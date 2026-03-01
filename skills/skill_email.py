import os
from typing import List, Dict, Any

# Import the IMAP and SMTP logic modules
from email_reader import IMAPReader
from email_sender import SMTPSender


class EmailSkill:
    """
    A Timus skill for reading emails via IMAP and sending emails via SMTP.
    Credentials are loaded from environment variables to avoid hard‑coding.
    """

    def __init__(self):
        # Load credentials securely
        self._creds = self._load_credentials()

        # Initialize IMAP reader
        self._imap_reader = IMAPReader(
            host=self._creds["imap_host"],
            port=self._creds["imap_port"],
            username=self._creds["username"],
            password=self._creds["password"],
            use_ssl=self._creds.get("imap_use_ssl", True),
        )

        # Initialize SMTP sender
        self._smtp_sender = SMTPSender(
            host=self._creds["smtp_host"],
            port=self._creds["smtp_port"],
            username=self._creds["username"],
            password=self._creds["password"],
            use_ssl=self._creds.get("smtp_use_ssl", True),
        )

    # --------------------------------------------------------------------- #
    # Credential loading
    # --------------------------------------------------------------------- #
    def _load_credentials(self) -> Dict[str, Any]:
        """
        Load email credentials from environment variables.
        Raises RuntimeError if any required variable is missing.
        """
        required_vars = [
            "EMAIL_IMAP_HOST",
            "EMAIL_IMAP_PORT",
            "EMAIL_SMTP_HOST",
            "EMAIL_SMTP_PORT",
            "EMAIL_USERNAME",
            "EMAIL_PASSWORD",
        ]

        creds: Dict[str, Any] = {}
        missing = []

        for var in required_vars:
            value = os.getenv(var)
            if value is None:
                missing.append(var)
            else:
                creds[var] = value

        if missing:
            raise RuntimeError(
                f"Missing required email credential environment variables: {', '.join(missing)}"
            )

        # Convert port strings to integers
        return {
            "imap_host": creds["EMAIL_IMAP_HOST"],
            "imap_port": int(creds["EMAIL_IMAP_PORT"]),
            "smtp_host": creds["EMAIL_SMTP_HOST"],
            "smtp_port": int(creds["EMAIL_SMTP_PORT"]),
            "username": creds["EMAIL_USERNAME"],
            "password": creds["EMAIL_PASSWORD"],
            "imap_use_ssl": True,
            "smtp_use_ssl": True,
        }

    # --------------------------------------------------------------------- #
    # IMAP read step
    # --------------------------------------------------------------------- #
    def read_emails(
        self,
        mailbox: str = "INBOX",
        limit: int = 10,
        since: str = None,
        before: str = None,
    ) -> List[Dict[str, Any]]:
        """
        Fetch recent emails from the specified mailbox.

        Parameters
        ----------
        mailbox : str
            Name of the mailbox to read from (default: "INBOX").
        limit : int
            Maximum number of emails to fetch (default: 10).
        since : str, optional
            RFC 822 date string; only return emails after this date.
        before : str, optional
            RFC 822 date string; only return emails before this date.

        Returns
        -------
        List[Dict[str, Any]]
            List of email metadata and body dictionaries.
        """
        return self._imap_reader.fetch_emails(
            mailbox=mailbox,
            limit=limit,
            since=since,
            before=before,
        )

    # --------------------------------------------------------------------- #
    # SMTP send step
    # --------------------------------------------------------------------- #
    def send_email(
        self,
        to_address: str,
        subject: str,
        body: str,
        cc: List[str] = None,
        bcc: List[str] = None,
        attachments: List[str] = None,
        reply_to: str = None,
        html_body: str = None,
    ) -> bool:
        """
        Send an email via SMTP.

        Parameters
        ----------
        to_address : str
            Recipient email address.
        subject : str
            Email subject line.
        body : str
            Plain‑text body of the email.
        cc : List[str], optional
            Carbon‑copy recipients.
        bcc : List[str], optional
            Blind carbon‑copy recipients.
        attachments : List[str], optional
            List of file paths to attach.
        reply_to : str, optional
            Reply‑to email address.
        html_body : str, optional
            HTML version of the email body.

        Returns
        -------
        bool
            True if the email was sent successfully, False otherwise.
        """
        return self._smtp_sender.send_email(
            to=to_address,
            subject=subject,
            body=body,
            cc=cc,
            bcc=bcc,
            attachments=attachments,
            reply_to=reply_to,
            html_body=html_body,
        )


**Explanation of the implementation**

1. **Secure credential handling** – All sensitive information (IMAP/SMTP hosts, ports, username, password) is read from environment variables. This prevents hard‑coding credentials in the source code.

2. **IMAP reading** – `read_emails` delegates to `IMAPReader.fetch_emails`, allowing optional filters such as `since` and `before`.

3. **SMTP sending** – `send_email` delegates to `SMTPSender.send_email` and supports CC, BCC, attachments, reply‑to, and HTML bodies.

4. **Timus‑compatible structure** – The class can be instantiated and its methods called as steps within a Timus skill workflow. The code is self‑contained and imports only the two logic modules (`email_reader` and `email_sender`), which should be implemented separately.