"""One-shot worker invoked by the optional Windows Scheduled Task."""
from sara_app.reminder_delivery import deliver_due_reminders


if __name__ == "__main__":
    result = deliver_due_reminders()
    print(f"SARA reminders: checked due items; delivered {result['delivered']} notification(s).")
