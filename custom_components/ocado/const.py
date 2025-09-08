"""Constants for Ocado Platform."""

CONF_EMAIL = 'email'
CONF_PASSWORD = 'password'
CONF_IMAP_SERVER = 'imap_server'
CONF_IMAP_PORT = 'imap_port'
CONF_EMAIL_FOLDER = 'folder'
CONF_SSL = 'ssl'
CONF_DAYS_OLD = 'days_old'

EMAIL_ATTR_FROM = 'from'
EMAIL_ATTR_SUBJECT = 'subject'
EMAIL_ATTR_BODY = 'body'
EMAIL_ATTR_DATE = 'my_date' # This 'my_date' is only used for the raw mail.date from mailparser

# --- IMPORTANT: These attribute names must match what you want to see in Home Assistant attributes ---
ATTR_ORDER_EMAIL_DATE = 'email_received_date'        # Changed from 'Email_Received_Date'
ATTR_ORDER_DELIVERY_DATE = 'delivery_date'          # Changed from 'Delivery_Date'
ATTR_ORDER_DELIVERY_TIME = 'delivery_time'          # Changed from 'Delivery_Time'
ATTR_ORDER_DELIVERY_COUNTDOWN = 'delivery_countdown' # Changed from 'Delivery_Countdown_Minutes'
ATTR_ORDER_EDIT_DATE = 'edit_until_date'            # Changed from 'Edit_Until_Date'
ATTR_ORDER_EDIT_TIME = 'edit_until_time'            # Changed from 'Edit_Until_Time'
ATTR_ORDER_EDIT_COUNTDOWN = 'edit_countdown'         # Changed from 'Edit_Countdown_Minutes'