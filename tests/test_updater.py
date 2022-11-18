"""Test the module :py:mod:`pydriosm._updater`."""

import pytest


def test__update_prepacked_data(monkeypatch, capfd):
    from pydriosm._updater import _update_prepacked_data

    monkeypatch.setattr('builtins.input', lambda _: "Yes")
    _update_prepacked_data(verbose=True)
    out, err = capfd.readouterr()
    assert "Done." in out and "Update finished." in out and "Failed." not in out


if __name__ == '__main__':
    pytest.main()
