#!/usr/bin/env python3
"""
Email Notification Module for Spotify Sync

Sends email notifications after sync runs complete.
Configure via environment variables in .env file.

Required environment variables:
    EMAIL_ENABLED=true
    EMAIL_SMTP_HOST=smtp.gmail.com
    EMAIL_SMTP_PORT=587
    EMAIL_SMTP_USER=your_email@gmail.com
    EMAIL_SMTP_PASSWORD=your_app_password
    EMAIL_TO=recipient@example.com
    EMAIL_FROM=your_email@gmail.com (optional, defaults to EMAIL_SMTP_USER)

Optional:
    EMAIL_SUBJECT_PREFIX=[Spotify Sync] (optional prefix for subject)
"""

import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import Optional, List


def is_email_enabled() -> bool:
    """Check if email notifications are enabled."""
    enabled = os.environ.get("EMAIL_ENABLED", "").lower()
    return enabled in ("true", "1", "yes", "on")


def get_email_config() -> Optional[dict]:
    """Get email configuration from environment variables."""
    if not is_email_enabled():
        return None
    
    required = ["EMAIL_SMTP_HOST", "EMAIL_SMTP_PORT", "EMAIL_SMTP_USER", 
                "EMAIL_SMTP_PASSWORD", "EMAIL_TO"]
    
    config = {}
    for key in required:
        value = os.environ.get(key)
        if not value:
            return None  # Missing required config
        config[key.lower().replace("email_", "")] = value
    
    # Optional: EMAIL_FROM (defaults to EMAIL_SMTP_USER)
    config["from"] = os.environ.get("EMAIL_FROM", config["smtp_user"])
    
    # Optional: Subject prefix
    config["subject_prefix"] = os.environ.get("EMAIL_SUBJECT_PREFIX", "[Spotify Sync]")
    
    # Convert port to int
    try:
        config["smtp_port"] = int(config["smtp_port"])
    except (ValueError, TypeError):
        config["smtp_port"] = 587  # Default
    
    return config


def send_email_notification(
    success: bool,
    log_output: str = "",
    summary: dict = None,
    error: Optional[Exception] = None
) -> bool:
    """
    Send email notification after sync run.
    
    Args:
        success: Whether the sync completed successfully
        log_output: Full log output from the sync
        summary: Optional dict with summary stats (e.g., tracks_added, playlists_updated)
        error: Optional exception if sync failed
    
    Returns:
        True if email sent successfully, False otherwise
    """
    config = get_email_config()
    if not config:
        return False
    
    try:
        # Build email content
        subject = f"{config['subject_prefix']} {'✅ Success' if success else '❌ Failed'}"
        
        # Build HTML body
        body_html = _build_email_body(success, log_output, summary, error)
        
        # Create message
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = config["from"]
        msg["To"] = config["to"]
        
        # Add HTML part
        html_part = MIMEText(body_html, "html")
        msg.attach(html_part)
        
        # Send email
        with smtplib.SMTP(config["smtp_host"], config["smtp_port"]) as server:
            server.starttls()
            server.login(config["smtp_user"], config["smtp_password"])
            server.send_message(msg)
        
        return True
        
    except Exception as e:
        # Don't raise - email failure shouldn't break the sync
        print(f"⚠️  Failed to send email notification: {e}")
        return False


def _build_email_body(
    success: bool,
    log_output: str,
    summary: dict = None,
    error: Optional[Exception] = None
) -> str:
    """Build HTML email body."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    status_icon = "✅" if success else "❌"
    status_text = "Success" if success else "Failed"
    status_color = "#28a745" if success else "#dc3545"
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 800px; margin: 0 auto; padding: 20px; }}
            .header {{ background-color: {status_color}; color: white; padding: 20px; border-radius: 5px 5px 0 0; }}
            .content {{ background-color: #f8f9fa; padding: 20px; border: 1px solid #dee2e6; }}
            .summary {{ background-color: white; padding: 15px; margin: 15px 0; border-radius: 5px; border-left: 4px solid {status_color}; }}
            .log {{ background-color: #2d2d2d; color: #f8f8f2; padding: 15px; border-radius: 5px; font-family: 'Courier New', monospace; font-size: 12px; overflow-x: auto; white-space: pre-wrap; }}
            .error {{ background-color: #fff3cd; border: 1px solid #ffc107; padding: 15px; border-radius: 5px; margin: 15px 0; }}
            .footer {{ text-align: center; color: #6c757d; font-size: 12px; margin-top: 20px; }}
            h1 {{ margin: 0; }}
            h2 {{ margin-top: 0; color: {status_color}; }}
            .stat {{ display: inline-block; margin: 5px 15px 5px 0; }}
            .stat-label {{ font-weight: bold; color: #6c757d; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>{status_icon} Spotify Sync {status_text}</h1>
                <p style="margin: 5px 0 0 0;">{timestamp}</p>
            </div>
            
            <div class="content">
    """
    
    # Add summary if available
    if summary:
        html += """
                <div class="summary">
                    <h2>📊 Summary</h2>
        """
        for key, value in summary.items():
            # Format key nicely
            label = key.replace("_", " ").title()
            html += f'<div class="stat"><span class="stat-label">{label}:</span> {value}</div>'
        html += """
                </div>
        """
    
    # Add error if failed
    if error:
        html += f"""
                <div class="error">
                    <h2>⚠️ Error</h2>
                    <pre>{str(error)}</pre>
                </div>
        """
    
    # Add log output
    if log_output:
        # Escape HTML and limit length
        log_escaped = log_output.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        # Show last 5000 characters if too long
        if len(log_escaped) > 5000:
            log_escaped = "... (truncated) ...\n" + log_escaped[-5000:]
        
        html += f"""
                <h2>📋 Log Output</h2>
                <div class="log">{log_escaped}</div>
        """
    
    html += """
            </div>
            
            <div class="footer">
                <p>This is an automated notification from your Spotify sync automation.</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    return html

