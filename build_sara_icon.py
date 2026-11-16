"""Build the Windows icon from the same geometric SARA mark as the SVG."""
from pathlib import Path
from PIL import Image, ImageDraw

def build():
    scale = 4
    image = Image.new('RGBA', (128 * scale, 128 * scale))
    draw = ImageDraw.Draw(image)
    box = lambda xy: tuple(v * scale for v in xy)
    draw.rounded_rectangle(box((0, 0, 127, 127)), 28 * scale, fill='#07121b')
    draw.ellipse(box((16, 16, 112, 112)), outline='#164656', width=5 * scale)
    for start, end in ((205, 315), (25, 135)):
        draw.arc(box((18, 18, 110, 110)), start, end, fill='#35e2f2', width=6 * scale)
    draw.line(box((83, 43, 50, 43, 43, 48, 43, 60, 50, 67, 78, 67, 85, 74, 85, 84, 78, 91, 44, 91)), fill='#d9fbff', width=10 * scale, joint='curve')
    draw.ellipse(box((102, 26, 114, 38)), fill='#ff984e')
    image.save(Path(__file__).parent / 'assets' / 'sara.ico', sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])

if __name__ == '__main__':
    build()
