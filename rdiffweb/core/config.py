# -*- coding: utf-8 -*-
# rdiffweb, A web interface to rdiff-backup repositories
# Copyright (C) 2012-2021 rdiffweb contributors
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import argparse
import logging
import re
import sys
from collections import OrderedDict

import cherrypy
import configargparse
import pkg_resources
from cherrypy import Application

# Define the logger
logger = logging.getLogger(__name__)

# Get rdiffweb version.
try:
    VERSION = pkg_resources.get_distribution("rdiffweb").version
except pkg_resources.DistributionNotFound:
    VERSION = "DEV"


def get_parser():
    # Get global config argument parser
    parser = configargparse.ArgumentParser(
        prog='rdiffweb',
        description='Web interface to browse and restore rdiff-backup repositories.',
        default_config_files=['/etc/rdiffweb/rdw.conf', '/etc/rdiffweb/rdw.conf.d/*.conf'],
        add_env_var_help=True,
        auto_env_var_prefix='RDIFFWEB_',
        config_file_parser_class=ConfigFileParser,
        conflict_handler='resolve',
    )

    parser.add_argument(
        '-f', '--config', is_config_file=True, metavar='FILE', help='location of Rdiffweb configuration file'
    )

    parser.add(
        '--database-uri',
        '--sqlitedb-file',
        '--sqlitedbfile',
        metavar='URI',
        help="""Location of the database used for persistence. SQLite and PostgreSQL
            database are supported officially. To use a SQLite database you may
            define the location using a file path or a URI.
            e.g.: /srv/rdiffweb/file.db or sqlite:///srv/rdiffweb/file.db`.
            To use PostgreSQL server you must provide
            a URI similar to postgresql://user:pass@10.255.1.34/dbname and you
            must install required dependencies.
            By default, Rdiffweb uses a SQLite embedded database located at
            /etc/rdiffweb/rdw.db.""",
        default='/etc/rdiffweb/rdw.db',
    )

    parser.add_argument(
        '-d',
        '--debug',
        action='store_true',
        help='enable rdiffweb debug mode - change the log level to DEBUG, print exception stack trace to the web interface and show SQL query in logs',
    )

    parser.add_argument(
        '--admin-user',
        '--adminuser',
        metavar='USERNAME',
        help='administrator username. The administrator user get created on startup if the database is empty.',
        default='admin',
    )

    parser.add_argument(
        '--admin-password',
        metavar='USERNAME',
        help="""administrator encrypted password as SSHA. Read online
            documentation to know more about how to encrypt your password
            into SSHA or use http://projects.marsching.org/weave4j/util/genpassword.php
            When defined, administrator password cannot be updated using the web interface.
            When undefined, default administrator password is `admin123` and
            it can be updated using the web interface.""",
    )

    parser.add_argument(
        '--default-theme',
        '--defaulttheme',
        help='define the default theme. Either: default, blue or orange. Define the CSS file to be loaded in the web interface. You may manually edit a CSS file to customize it. The location is similar to `/usr/local/lib/python3.9/dist-packages/rdiffweb/static/`',
        choices=['default', 'blue', 'orange'],
        default='default',
    )

    parser.add_argument(
        '--environment',
        choices=['development', 'production'],
        help='define the type of environment: development, production. This is used to limit the information shown to the user when an error occur.',
        default='production',
    )

    parser.add_argument(
        '--email-encryption',
        '--emailencryption',
        choices=['none', 'ssl', 'starttls'],
        help='type of encryption to be used when establishing communication with SMTP server. Default: none',
        default='none',
    )

    parser.add_argument(
        '--email-host',
        '--emailhost',
        metavar='HOST',
        help='SMTP server used to send email in the form <host>:<port>. If the port is not provided, default to standard port 25 or 465 is used. e.g.: smtp.gmail.com:587',
    )

    parser.add_argument(
        '--email-sender',
        '--emailsender',
        metavar='EMAIL',
        help='email addres used for the `from:` field when sending email.',
    )

    parser.add_argument(
        '--email-notification-time',
        '--emailnotificationtime',
        metavar='TIME',
        help='time when the email notifcation should be sent for inactive backups. e.g.: 22:00 Default value: 23:00',
        default='23:00',
    )















    parser.add('--server-host', '--serverhost', metavar='IP', default='127.0.0.1', help='IP address to listen to')

    parser.add(
        '--server-port',
        '--serverport',
        metavar='PORT',
        help='port to listen to for HTTP request',
        default='8080',
        type=int,
    )



    parser.add(
        '--ssl-certificate',
        '--sslcertificate',
        metavar='CERT',
        help='location of the SSL Certification to enable HTTPS (not recommended)',
    )

    parser.add(
        '--ssl-private-key',
        '--sslprivatekey',
        metavar='KEY',
        help='location of the SSL Private Key to enable HTTPS (not recommended)',
    )

    parser.add(
        '--tempdir',
        metavar='FOLDER',
        help='alternate temporary folder to be used when restoring files. Might be useful if the default location has limited disk space. Default to TEMPDIR environment or `/tmp`.',
    )

    parser.add(
        '--disable-ssh-keys',
        action='store_true',
        help='used to hide SSH Key management to avoid users to add or remove SSH Key using the web application',
        default=False,
    )

    parser.add(
        '--password-min-length',
        type=int,
        help="Minimum length of the user's password",
        default=8,
    )

    parser.add(
        '--password-max-length',
        type=int,
        help="Maximum length of the user's password",
        default=128,
    )

    parser.add(
        '--password-score',
        type=lambda x: max(1, min(int(x), 4)),
        help="Minimum zxcvbn's score for password. Value from 1 to 4. Default value 2. Read more about it here: https://github.com/dropbox/zxcvbn",
        default=2,
    )

    parser.add_argument('--version', action='version', version='%(prog)s ' + VERSION)

    # Here we append a list of arguments for each locale.
    flags = ['--welcome-msg'] + ['--welcome-msg-' + i for i in ['ca', 'en', 'es', 'fr', 'ru']] + ['--welcomemsg']
    parser.add_argument(
        *flags,
        metavar='HTML',
        help='replace the welcome message displayed in the login page for default locale or for a specific locale',
        action=LocaleAction
    )
    return parser


def parse_args(args=None, config_file_contents=None):
    args = sys.argv[1:] if args is None else args
    return get_parser().parse_args(args, config_file_contents=config_file_contents)


class LocaleAction(argparse.Action):
    """
    Custom Action to support defining arguments with locale.
    """

    def __init__(self, option_strings, dest, nargs=None, **kwargs):
        super(LocaleAction, self).__init__(option_strings, dest, **kwargs)

    def __call__(self, parser, namespace, value, option_string=None):
        if option_string[-3] == '-':
            # When using arguments, we can extract the locale from the argument key
            locale = option_string[-2:]
        elif value[2] == ':':
            # When using config file, the locale could be extract from the value e.g. fr:message
            locale = value[0:2]
            value = value[3:]
        else:
            locale = ''
        # Create a dictionary with locale.
        items = getattr(namespace, self.dest) or {}
        items[locale] = value
        setattr(namespace, self.dest, items)


class ConfigFileParser(object):
    """
    Custom config file parser to support rdiffweb config file format.
    """

    def get_syntax_description(self):
        msg = "Configuration file syntax allows: key=value, flag=true."
        return msg

    def parse(self, stream):
        """
        Used to read the rdiffweb config file as dict.
        """

        result = OrderedDict()

        for i, line in enumerate(stream):
            line = re.compile("(.*?)#.*").sub(r'\1', line).strip()
            if not line:
                continue
            if '=' not in line:
                raise configargparse.ConfigFileParserException(
                    "Unexpected line {} in {}: {}".format(i, getattr(stream, 'name', 'stream'), line)
                )
            split_line = line.partition('=')
            if not len(split_line) == 3:
                raise configargparse.ConfigFileParserException(
                    "Unexpected line {} in {}: {}".format(i, getattr(stream, 'name', 'stream'), line)
                )

            # Get key a& value
            key = split_line[0].lower().strip().replace('_', '-')
            value = split_line[2].strip()

            # Support welcome-msg locale for backward compatibility
            m = re.match("welcome-?msg\\[(ca|en|es|fr|ru)\\]", key.lower())
            if m:
                key = "welcome-msg-" + m.group(1)
                value = m.group(1) + ":" + value

            result[key] = value

        # This dictionary is read by cherrypy. So create appropriate structure.
        return result


class Option(object):
    def __init__(self, key):
        assert key
        self.key = key

    def __get__(self, instance, owner):
        """
        Return a property to wrap the given option.
        """
        return self.get(instance)

    def get(self, instance=None):
        """
        Return the value of this options.
        """
        if isinstance(instance, Application):
            app = instance
        else:
            app = cherrypy.request.app or getattr(instance, 'app', None)
        assert app, "Option() can't get reference to app"
        assert app.cfg, "Option() can't get reference to app.cfg"
        return getattr(app.cfg, self.key)
