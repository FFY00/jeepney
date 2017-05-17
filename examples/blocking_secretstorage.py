"""Example accessing the SecretStorage DBus interface with blocking APIs

https://freedesktop.org/wiki/Specifications/secret-storage-spec/secrets-api-0.1.html#ref-dbus-api
"""

from jeepney import new_method_call, DBusObject, Properties
from jeepney.integrate.blocking import connect_and_authenticate

secrets = DBusObject('/org/freedesktop/secrets',
                           bus_name= 'org.freedesktop.secrets',
                           interface='org.freedesktop.Secret.Service')

login_keyring = DBusObject('/org/freedesktop/secrets/collection/login',
                           bus_name= 'org.freedesktop.secrets',
                           interface='org.freedesktop.Secret.Collection')

msg = new_method_call(login_keyring, 'SearchItems', 'a{ss}',
                      ([
                          ('user', 'tk2e15'),
                      ],)
                     )


conn = connect_and_authenticate(bus='SESSION')

resp = conn.send_and_get_reply(Properties(secrets).get('Collections'))
print('Collections:', resp.body[0][1])

resp = conn.send_and_get_reply(msg)
print('Search res:', resp)
