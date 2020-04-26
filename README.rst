This is a low-level, pure Python DBus protocol client. It has an `I/O-free
<https://sans-io.readthedocs.io/>`__ core, and integration modules for different
event loops.

DBus is an inter-process communication system, mainly used in Linux.

`Jeepney docs on Readthedocs <https://jeepney.readthedocs.io/en/latest/>`__

This project is experimental, and there are a
number of `more mature Python DBus bindings <https://www.freedesktop.org/wiki/Software/DBusBindings/#python>`__.

This project uses ``pyproject.toml``, if you need a ``setup.py`` you can generate it with ``dephell``.

::

    dephell deps convert
