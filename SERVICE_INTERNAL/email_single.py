"""
------------------------------------------------------------
#   SEND SINGLE EMAIL ONLY SECTION  
------------------------------------------------------------
"""
from SERVICE_INTERNAL.abstract import info_logger


def _try_send_login_email(user: object):
    """
    Receives the user queryset and look for the login alert
    if found, send email, else just comot eye
    #   LOGGER ALREADY SET UP
    """
    
    if user.receive_email_login_alert:
        #send mail
        info_logger(msg=f"EMAIL: successfully sent login alert to {user.email} as they have reminder enanbled in their account")
    else:
        info_logger(msg=f"LOGIN ALERT: {user.email} logged in but no login alert was sent as they have it disabled")