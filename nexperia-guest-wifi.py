"""
MIT License

Copyright (c) 2022 Jeroen Koeter

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

#!/usr/bin/python

from datetime import datetime, timezone
from hashlib import sha256
import re
import xml.etree.ElementTree as ET
import requests
import argparse


class Router(object):
    """This class executes commands on a Nexperia V10 router."""

    def __init__(self, host, username, password):
        self.host = host
        self.username = username
        self.password = password
        self.session = None
        self.session_token = None
        self.session_token_ext = None

    def login(self):
        """Login the Nexperia router"""
        self.session = requests.Session()

        token_url = 'http://{}/function_module/login_module/login_page/logintoken_lua.lua'.format(self.host)
        login_url = 'http://{}'.format(self.host)

        # 1st stage login to get the required cookies; result can be ignored
        self.session.get(login_url)
        # 2nd stage login to get the password token
        result = self.session.get(token_url)
        self.session_token = re.findall(r'\d+', result.text)[0]
        data = {
            "Username": self.username,
            "Password": sha256((self.password + self.session_token).encode('utf-8')).hexdigest(),
            "action": "login"
        }
        # 3rd stage login; send the username plus hashed password
        result = self.session.post(login_url, data)

    def logout(self):
        logout_url = 'http://{}'.format(self.host)
        self.session.post(logout_url, data={
            "IF_LogOff": 1,
            "IF_LanguageSwitch": "",
            "IF_ModeSwitch": ""
        })
        self.session = None

    def get_guest_wifi_enabled(self):
        if not self.session:
            self.login()

        # Get the guest-wifi data
        # Generate a timestamp for the request
        ts = round(datetime.now(timezone.utc).timestamp() * 1000)
        # you need to get this page before getting the data otherwise it fails with page not found...
        # and you need the secret seesionTmpToken when writing
        guest_wifi_page = self.session.get('http://{}/getpage.lua?pid=123&nextpage=Localnet_Wlan_GuestWiFi_t.lp&Menu3Location=0&_={}'.format(self.host, ts))
        # Get the extended session-key
        session_token_ext_string = re.findall('_sessionTmpToken = \"(.+)\"', guest_wifi_page.text)[0]
        # format the string-encoded byte-string in a real character-string
        self.session_token_ext = ''
        char_count = len(session_token_ext_string)//4
        for count in range(char_count):
            self.session_token_ext = self.session_token_ext + chr(int(session_token_ext_string[(count*4)+2:(count*4)+4], 16))

        # Update the timestamp and add a little delay as the returned time is in seconds and we use miliseconds
        ts = round(datetime.now(timezone.utc).timestamp() * 1000) + 48
        # Get the page with the guest-wifi data
        data_page = self.session.get('http://{}/common_page/Localnet_Wlan_GuestWiFiOnOff_lua.lua?_={}'.format(self.host, ts+35))
        # Parse the XML to get the current status
        result_root = ET.fromstring(data_page.text)
        guest_wifi_switch = result_root.find('OBJ_GUESTWIFISWITCH_ID')
        guest_wifi_settings = {}
        if guest_wifi_switch:
            param_list = guest_wifi_switch.findall('Instance/ParaName')
            value_list = guest_wifi_switch.findall('Instance/ParaValue')
            for count, parameter in enumerate(param_list):
                guest_wifi_settings[parameter.text] = int(value_list[count].text)

        return guest_wifi_settings['Enable'] == 1

    def set_guest_wifi_enable(self, enable=True):
        if not self.session:
            self.login()

        current_state = self.get_guest_wifi_enabled()

        if current_state != enable:
            set_data_url = 'http://{}/common_page/Localnet_Wlan_GuestWiFiOnOff_lua.lua'.format(self.host)
            result = self.session.post(set_data_url, data={
                "IF_ACTION": "Apply",
                "_InstID": "",
                "Enable": 1 if enable else 0,
                "Btn_cancel_GuestWiFiOnOff": "",
                "Btn_apply_GuestWiFiOnOff": "",
                "_sessionTOKEN": self.session_token_ext
            })


if __name__ == '__main__':
    parser = argparse.ArgumentParser('nexperia-guest-wifi')
    parser.add_argument('-i', '--host', help='the host-name/IP-address of the Nexperia router')
    parser.add_argument('-u', '--user', help='the user-name for login (Admin)')
    parser.add_argument('-p', '--pwd',  help='the password for the user')
    parser.add_argument('state', nargs='?', help='set the state of the guest-wifi (on or off); \
                                                  if not specified the current state is obtained')

    args = parser.parse_args()

    if not args.host:
        print('error: no host specified')
        exit()

    if not args.user:
        print('error: no user-name specified')
        exit()

    if not args.pwd:
        print('error: no password specified')
        exit()

    my_router = Router(args.host, args.user, args.pwd)
    if not args.state:
        guest_wifi_on = my_router.get_guest_wifi_enabled()
        print('Guest-Wifi is: {}'.format('on' if guest_wifi_on else 'off'))
    else:
        if args.state.upper() == 'ON':
            my_router.set_guest_wifi_enable(True)
        elif args.state.upper() == 'OFF':
            my_router.set_guest_wifi_enable(False)
        else:
            print('Invalid state: \'{}\'. Use \'On\' or \'Off\''.format(args.state))
