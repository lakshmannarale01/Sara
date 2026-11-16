$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$request = [Console]::In.ReadToEnd() | ConvertFrom-Json
# Core Audio endpoint interfaces and media virtual keys are fixed Windows APIs:
# https://learn.microsoft.com/windows/win32/api/endpointvolume/nn-endpointvolume-iaudioendpointvolume
# https://learn.microsoft.com/windows/win32/api/winuser/nf-winuser-sendinput
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
using System.ComponentModel;
namespace SaraSystemAudio {
  [ComImport, Guid("BCDE0395-E52F-467C-8E3D-C4579291692E")] class Enumerator {}
  [ComImport, InterfaceType(ComInterfaceType.InterfaceIsIUnknown), Guid("A95664D2-9614-4F35-A746-DE8DB63617E6")]
  interface IEnumerator {
    [PreserveSig] int EnumAudioEndpoints(int flow, uint mask, out IntPtr devices);
    [PreserveSig] int GetDefaultAudioEndpoint(int flow, int role, out IDevice device);
  }
  [ComImport, InterfaceType(ComInterfaceType.InterfaceIsIUnknown), Guid("D666063F-1587-4E43-81F1-B948E807363F")]
  interface IDevice {
    [PreserveSig] int Activate(ref Guid iid, uint context, IntPtr parameters, [MarshalAs(UnmanagedType.IUnknown)] out object volume);
  }
  [ComImport, InterfaceType(ComInterfaceType.InterfaceIsIUnknown), Guid("5CDF2C82-841E-4546-9722-0CF74078229A")]
  interface IVolume {
    [PreserveSig] int RegisterControlChangeNotify(IntPtr callback);
    [PreserveSig] int UnregisterControlChangeNotify(IntPtr callback);
    [PreserveSig] int GetChannelCount(out uint count);
    [PreserveSig] int SetMasterVolumeLevel(float value, ref Guid context);
    [PreserveSig] int SetMasterVolumeLevelScalar(float value, ref Guid context);
    [PreserveSig] int GetMasterVolumeLevel(out float value);
    [PreserveSig] int GetMasterVolumeLevelScalar(out float value);
    [PreserveSig] int SetChannelVolumeLevel(uint channel, float value, ref Guid context);
    [PreserveSig] int SetChannelVolumeLevelScalar(uint channel, float value, ref Guid context);
    [PreserveSig] int GetChannelVolumeLevel(uint channel, out float value);
    [PreserveSig] int GetChannelVolumeLevelScalar(uint channel, out float value);
    [PreserveSig] int SetMute([MarshalAs(UnmanagedType.Bool)] bool muted, ref Guid context);
    [PreserveSig] int GetMute([MarshalAs(UnmanagedType.Bool)] out bool muted);
  }
  public class AudioResult {
    public int volume; public bool muted; public int requested_level;
    public bool readback_verified; public bool changed;
  }
  public static class Core {
    static void Check(int code) { Marshal.ThrowExceptionForHR(code); }
    public static AudioResult Control(string command, int level) {
      IEnumerator enumerator = null; IDevice device = null; IVolume volume = null;
      try {
        enumerator = (IEnumerator)new Enumerator();
        Check(enumerator.GetDefaultAudioEndpoint(0, 1, out device));
        Guid iid = typeof(IVolume).GUID; object activated;
        Check(device.Activate(ref iid, 23, IntPtr.Zero, out activated));
        volume = (IVolume)activated;
        float before; bool wasMuted;
        Check(volume.GetMasterVolumeLevelScalar(out before)); Check(volume.GetMute(out wasMuted));
        int target = (int)Math.Round(before * 100); Guid context = Guid.Empty;
        bool desiredMute = wasMuted; bool volumeChange = false; bool muteChange = false;
        switch (command) {
          case "read": break;
          case "set_volume": target = level; volumeChange = true; break;
          case "volume_up": target = Math.Min(100, target + 10); volumeChange = true; break;
          case "volume_down": target = Math.Max(0, target - 10); volumeChange = true; break;
          case "mute": desiredMute = true; muteChange = true; break;
          case "unmute": desiredMute = false; muteChange = true; break;
          default: throw new ArgumentException("Unsupported audio command.");
        }
        if (target < 0 || target > 100) throw new ArgumentException("Invalid volume.");
        if (volumeChange) Check(volume.SetMasterVolumeLevelScalar(target / 100f, ref context));
        if (muteChange) Check(volume.SetMute(desiredMute, ref context));
        float after; bool isMuted;
        Check(volume.GetMasterVolumeLevelScalar(out after)); Check(volume.GetMute(out isMuted));
        int actual = (int)Math.Round(after * 100);
        return new AudioResult {volume=actual, muted=isMuted, requested_level=target,
          changed=Math.Abs(after-before) > 0.00001 || isMuted != wasMuted,
          readback_verified=(!volumeChange || Math.Abs(actual-target)<=1) && (!muteChange || isMuted==desiredMute)};
      } finally {
        if (volume != null) Marshal.ReleaseComObject(volume);
        if (device != null) Marshal.ReleaseComObject(device);
        if (enumerator != null) Marshal.ReleaseComObject(enumerator);
      }
    }
  }
  [StructLayout(LayoutKind.Sequential)] struct KeyboardInput {
    public ushort key; public ushort scan; public uint flags; public uint time; public UIntPtr extra;
  }
  [StructLayout(LayoutKind.Sequential)] struct MouseInput {
    public int x; public int y; public uint data; public uint flags; public uint time; public UIntPtr extra;
  }
  [StructLayout(LayoutKind.Explicit)] struct InputUnion {
    [FieldOffset(0)] public KeyboardInput keyboard; [FieldOffset(0)] public MouseInput mouse;
  }
  [StructLayout(LayoutKind.Sequential)] struct Input {public uint type; public InputUnion data;}
  public static class Media {
    [DllImport("user32.dll", SetLastError=true)] static extern uint SendInput(uint count, Input[] inputs, int size);
    public static void Send(string command) {
      ushort key;
      switch(command) {
        case "next_track": key=0xB0; break;
        case "previous_track": key=0xB1; break;
        case "stop": key=0xB2; break;
        case "play_pause": key=0xB3; break;
        default: throw new ArgumentException("Unsupported media command.");
      }
      Input[] inputs = new Input[2];
      inputs[0].type=1; inputs[0].data.keyboard.key=key;
      inputs[1].type=1; inputs[1].data.keyboard.key=key; inputs[1].data.keyboard.flags=2;
      if (SendInput(2, inputs, Marshal.SizeOf(typeof(Input))) != 2) throw new Win32Exception(Marshal.GetLastWin32Error());
    }
  }
}
'@
$command = [string]$request.command
if ($command -in @('play_pause', 'next_track', 'previous_track', 'stop')) {
    [SaraSystemAudio.Media]::Send($command)
    @{available=$true; key_sent=$true; playback_verified=$false; command=$command} | ConvertTo-Json -Compress
} else {
    $level = 0
    if ($command -eq 'set_volume') {
        if ($request.level -isnot [int] -and $request.level -isnot [long]) { throw 'Invalid volume.' }
        $level = [int]$request.level
    }
    $state = [SaraSystemAudio.Core]::Control($command, $level)
    @{available=$true; volume=$state.volume; muted=$state.muted; requested_level=$state.requested_level; readback_verified=$state.readback_verified; changed=$state.changed; command=$command} | ConvertTo-Json -Compress
}
