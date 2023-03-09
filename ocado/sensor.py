"""Ocado EMail Digester"""
from datetime import timedelta, date, datetime, timezone
import logging
import re
from bs4 import BeautifulSoup

from imapclient import IMAPClient
from mailparser import parse_from_bytes
import voluptuous as vol

from homeassistant.components.sensor import PLATFORM_SCHEMA
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity import Entity

from .const import (
    CONF_EMAIL, CONF_PASSWORD, CONF_IMAP_SERVER,
    CONF_IMAP_PORT, CONF_SSL, CONF_EMAIL_FOLDER, CONF_DAYS_OLD,
    EMAIL_ATTR_FROM, EMAIL_ATTR_SUBJECT,
    EMAIL_ATTR_BODY, EMAIL_ATTR_DATE,
    ATTR_ORDER_EMAIL_DATE, ATTR_ORDER_DELIVERY_DATE, ATTR_ORDER_DELIVERY_TIME, ATTR_ORDER_EDIT_DATE, ATTR_ORDER_EDIT_TIME, ATTR_ORDER_EDIT_COUNTDOWN)

_LOGGER = logging.getLogger(__name__)

# Scan every 10 minutes
SCAN_INTERVAL = timedelta(seconds=10*60)

EMAIL_DOMAIN = 'ocado.com'
ORDER_EMAIL_DATE = 'date'
ORDER_DELIVERY_DATE = 'date'
ORDER_DELIVERY_TIME = 'date'
ORDER_EDIT_DATE = 'date'
ORDER_EDIT_TIME = 'date'
ORDER_EDIT_COUNTDOWN = 'date'

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_EMAIL): cv.string,
    vol.Required(CONF_PASSWORD): cv.string,
    vol.Required(CONF_DAYS_OLD, default='7'): cv.positive_int,
    vol.Required(CONF_IMAP_SERVER, default='imap.gmail.com'): cv.string,
    vol.Required(CONF_IMAP_PORT, default=993): cv.positive_int,
    vol.Required(CONF_SSL, default=True): cv.boolean,
    vol.Required(CONF_EMAIL_FOLDER, default='INBOX'): cv.string,
})

# Ocado Dates are various and need to be normalised to enable comparison

def check_delivery_edit_status(Order_Delivery_Date, Order_Edit_Until_Date, Order_Edit_Until_Time):
 # remove any spaces that can break the process
 Order_Delivery_Date = Order_Delivery_Date.strip()
 Order_Edit_Until_Date = Order_Edit_Until_Date.strip()
 Order_Edit_Until_Time = Order_Edit_Until_Time.strip()
 # Get Current Month and Year to enable compare and set TZ to UTC
 current_date = datetime.now()
 current_date = current_date.replace(tzinfo=timezone.utc)
 current_month = current_date.strftime("%m")

# Order Edit Until Date Object and set TZ to UTC
 Order_Edit_Until_Date_Time_object = datetime.strptime(Order_Edit_Until_Date + ' ' + Order_Edit_Until_Time, '%A %d %B %H:%M')
 Order_Edit_Until_Date_Time_object = Order_Edit_Until_Date_Time_object.replace(tzinfo=timezone.utc)
 Order_Edit_Until_Date_Time_object = Order_Edit_Until_Date_Time_object.replace(year=datetime.now().year)
 
 Order_Delivery_Date_object = datetime.strptime(Order_Delivery_Date, '%A %d %B')
 Order_Delivery_Date_object = Order_Delivery_Date_object.replace(tzinfo=timezone.utc)
 Order_Delivery_Date_object = Order_Delivery_Date_object + timedelta(hours=23, minutes=59) # set to end of the day
 Order_Delivery_Date_object = Order_Delivery_Date_object.replace(year=datetime.now().year)

# Make educated guess of the year as we added the current year
# Check if current month is December and Order_Delivery_Date is January then increment Year
 if (current_month == '12')  and (Order_Delivery_Date_object.strftime("%m") == '01') :
     Order_Delivery_Date_object = Order_Delivery_Date_object.replace(year=datetime.now().year+1)

# Make educated guess of the year as we added the current year
# Check if current month is December and Order_Edit_Date is January then increment Year
 if (current_month == '12')  and (Order_Edit_Until_Date_Time_object.strftime("%m") == '01') :
     Order_Edit_Until_Date_Time_object = Order_Edit_Until_Date_Time_object.replace(year=datetime.now().year+1)

 _LOGGER.debug('         Current Date:' + current_date.strftime(f'%H:%M %A %d %B %Y'))
 _LOGGER.debug('  Order Delivery Date:' + Order_Delivery_Date_object.strftime(f'%H:%M %A %d %B %Y'))
 _LOGGER.debug('Order Edit Until Date:' + Order_Edit_Until_Date_Time_object.strftime(f'%A %d %B %Y'))
 _LOGGER.debug('Order Edit Until Time:' + Order_Edit_Until_Date_Time_object.strftime(f'%H:%M %A %d %B %Y'))

 if (current_date > Order_Edit_Until_Date_Time_object):
     Edit_Status = False
 else:
     Edit_Status = True

 if (current_date > Order_Delivery_Date_object):
     Delivery_Status = False
 else:
     Delivery_Status = True

# check how close we are to edit list closing time

 Edit_Countdown = ((Order_Edit_Until_Date_Time_object - current_date) // timedelta(minutes=1))

 _LOGGER.debug('Order Edit Summary:' + str(Edit_Countdown))

 return (Edit_Status, Delivery_Status, Edit_Countdown)

# Main function for Ocado
def ocado(email, subject, email_date):
# Only look at Order Confirmation EMails    
    if (subject != 'Confirmation of your order'):
     return
    _LOGGER.debug('In ocado processing; ' + subject)

    try:
     global ORDER_EMAIL_DATE
     global ORDER_DELIVERY_DATE
     global ORDER_DELIVERY_TIME
     global ORDER_EDIT_DATE
     global ORDER_EDIT_TIME
     global ORDER_EDIT_COUNTDOWN
     """Parse Ocado Order details."""
     order_delivery_date = ""
     order_delivery_time = ""
     order_edit_time = ""
     order_edit_date = ""
    
     soup = BeautifulSoup(email[EMAIL_ATTR_BODY], 'html.parser')
     elements = soup.find_all('td')

     for idx, element in enumerate(elements):
         text = element.getText()
         if(idx == 3):  # Delivery Time
             order_delivery_time = text
         if(idx == 5):  # Delivery Date
             order_delivery_date = text
     # Edit Order Text only element with em fortunately
     child_soup = soup.find_all('em')
     text = 'You can edit'
     for i in child_soup:
       my_edit = i.string
         # clean up the edit order string
       find_until = (re.search('until', str(my_edit)))
       find_end = (re.search('.', str(my_edit)))
       edit_order = (my_edit[find_until.start()+6:find_end.start()-1])
       find_on = (re.search('on', str(edit_order)))
       order_edit_time = (edit_order[0:find_on.start()])
       order_edit_date = (edit_order[find_on.start()+2:])
       order_edit_date = order_edit_date.strip()

     _LOGGER.debug('Found delivery_date:' + order_delivery_date)
     _LOGGER.debug('Found delivery_time:' + order_delivery_time)
     _LOGGER.debug('Found order_edit_date:' + order_edit_date)
     _LOGGER.debug('Found order_edit_time:' + order_edit_time)

     # Clean up the Order Edit Date formatting so it displays nicer in the dashboard
     order_edit_date_obj = datetime.strptime(re.sub('(\d+)(st|nd|rd|th)', '\g<1>', order_edit_date), '%d %B %Y')
     order_edit_date_obj_string = order_edit_date_obj.strftime(f'%A %d %B')

     order_delivery_date_object = datetime.strptime(order_delivery_date, '%A %d %B')
     order_delivery_date_obj_string = order_delivery_date_object.strftime(f'%A %d %B')

     # Load delivery date, time and order edit date and time
     ORDER_EMAIL_DATE = email_date
     ORDER_DELIVERY_DATE = order_delivery_date_obj_string
     ORDER_DELIVERY_TIME = order_delivery_time
     ORDER_EDIT_DATE = order_edit_date_obj_string
     ORDER_EDIT_TIME = order_edit_time

     _LOGGER.debug('Send Delivery_date:' + order_delivery_date_obj_string)
     _LOGGER.debug('Send Edit_Date:' + order_edit_date_obj_string)
     _LOGGER.debug('Send Edit_Time:' + order_edit_time)

     # Check if Order can be edited or has been delivered
     Edit_Status, Delivery_Status, Edit_Summary = check_delivery_edit_status(ORDER_DELIVERY_DATE, ORDER_EDIT_DATE, ORDER_EDIT_TIME)
     if (Edit_Status == False):
        ORDER_EDIT_DATE = 'Not Available'
        ORDER_EDIT_TIME = ' '
     if (Delivery_Status == False):
        ORDER_DELIVERY_DATE = 'Not Available'
        ORDER_DELIVERY_TIME = ' '      
     ORDER_EDIT_COUNTDOWN = Edit_Summary

    except Exception as err:
      _LOGGER.error('Ocado process error {}'.format(err))
    return


def setup_platform(hass, config, add_entities, discovery_info=None):
    """Set up the Email platform."""
    add_entities([EmailEntity(config)], True)

class EmailEntity(Entity):
    """Email Entity."""

    def __init__(self, config):
        """Init the Email Entity."""
        self._attr = {
        }

        self.imap_server = config[CONF_IMAP_SERVER]
        self.imap_port = config[CONF_IMAP_PORT]
        self.email_address = config[CONF_EMAIL]
        self.password = config[CONF_PASSWORD]
        self.email_folder = config[CONF_EMAIL_FOLDER]
        self.ssl = config[CONF_SSL]
        self.days_old = int(config[CONF_DAYS_OLD])

        self.flag = [u'SINCE', date.today() - timedelta(days=self.days_old)]

    def update(self):
        """Update data from Email API."""
        self._attr = {
        }

        # update to current day
        self.flag = [u'SINCE', date.today() - timedelta(days=self.days_old)]

        emails = []
        server = IMAPClient(self.imap_server, use_uid=True, ssl=self.ssl)

        try:
            server.login(self.email_address, self.password)
            server.select_folder(self.email_folder, readonly=True)
        except Exception as err:
            _LOGGER.error('IMAPClient login error {}'.format(err))
            return False

        try:
            messages = server.search(self.flag)
            for uid, message_data in server.fetch(messages, 'RFC822').items():
                try:
                    mail = parse_from_bytes(message_data[b'RFC822'])
                    
                    emails.append({
                        EMAIL_ATTR_FROM: mail.from_,
                        EMAIL_ATTR_SUBJECT: mail.subject,
                        EMAIL_ATTR_BODY: mail.body,
                        EMAIL_ATTR_DATE: mail.Date,
                    })
                    _LOGGER.debug("Subject;" + mail.subject)
                    _LOGGER.debug("Date;" + mail.Date)

                except Exception as err:
                    _LOGGER.warning(
                        'mailparser parse_from_bytes error: {}'.format(err))

        except Exception as err:
            _LOGGER.error('IMAPClient update error: {}'.format(err))

        for email in emails:
            email_from = email[EMAIL_ATTR_FROM]
            email_subject = email[EMAIL_ATTR_SUBJECT]
            email_my_date = email[EMAIL_ATTR_DATE]
            if isinstance(email_from, (list, tuple)):
                email_from = list(email_from)
                email_from = ''.join(list(email_from[0]))

            if EMAIL_DOMAIN in email_from:
               ocado(email=email, subject=email_subject, email_date=email_my_date)
               	# Order Email Received Date: Thu, 23 Feb 2023 17:49:09 +0000 (GMT)
                # Order Delivery Date: Friday 24 February
                # Order Delivery Time: 12:00pm - 1:00pm
                # Order Edit Until Date: 23rd February 2023
                # Order Edit Until Time: 18:25 
               self._attr[ATTR_ORDER_EMAIL_DATE] = ORDER_EMAIL_DATE
               self._attr[ATTR_ORDER_DELIVERY_DATE] = ORDER_DELIVERY_DATE
               self._attr[ATTR_ORDER_DELIVERY_TIME] = ORDER_DELIVERY_TIME
               self._attr[ATTR_ORDER_EDIT_DATE] = ORDER_EDIT_DATE
               self._attr[ATTR_ORDER_EDIT_TIME] = ORDER_EDIT_TIME
               self._attr[ATTR_ORDER_EDIT_COUNTDOWN] = ORDER_EDIT_COUNTDOWN

        server.logout()

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._attr[ORDER_EDIT_COUNTDOWN]
    @property
    def state(self):
        """Return the state of the sensor."""
        return self._attr[ATTR_ORDER_EMAIL_DATE]
    @property
    def state(self):
        """Return the state of the sensor."""
        return self._attr[ATTR_ORDER_DELIVERY_DATE]
    @property
    def state(self):
        """Return the state of the sensor."""
        return self._attr[ATTR_ORDER_DELIVERY_TIME]
    @property
    def state(self):
        """Return the state of the sensor."""
        return self._attr[ATTR_ORDER_EDIT_DATE]
    @property
    def state(self):
        """Return the state of the sensor."""
        return self._attr[ATTR_ORDER_EDIT_TIME]

    @property
    def name(self):
        """Return the name of the sensor."""
        return 'ocado_tracking'

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        return self._attr

    @property
    def icon(self):
        """Return the icon to use in the frontend."""
        return 'mdi:truck'
