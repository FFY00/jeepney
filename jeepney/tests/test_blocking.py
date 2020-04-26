import pytest

from jeepney import DBusAddress
from jeepney.bus_messages import DBus
from jeepney.integrate.blocking import *
from jeepney.low_level import HeaderFields, MessageType
from jeepney.wrappers import new_method_call


class MethodCalledException(Exception):
    pass


@pytest.fixture(params=['SESSION'])
def connection(request):
    conn = connect_and_authenticate(request.param)

    yield conn

    conn.close()


@pytest.fixture()
def server(connection, name='com.example.object'):
    dbus = DBus()

    reply = connection.send_and_get_reply(dbus.RequestName(name))
    assert reply == (1,)

    yield connection, name

    connection.send_and_get_reply(dbus.ReleaseName(name))


def test_connect(connection):
    pass


def test_send_and_get_reply(connection):
    dbus = DBus()
    connection.send_and_get_reply(dbus.RequestName('com.example.test'))


def test_handle(server):
    path = '/test'
    method = 'test'

    conn, name = server

    def handle(msg):
        hdr = msg.header
        if (
            hdr.message_type == MessageType.method_call and
            hdr.fields[HeaderFields.path] == path and
            hdr.fields[HeaderFields.member] == method
        ):
            raise MethodCalledException

    conn.router.on_unhandled = handle

    conn.send_message(new_method_call(DBusAddress(path, name), method))

    with pytest.raises(MethodCalledException):
        conn.recv_messages()
