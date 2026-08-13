"""Unit tests for sap_gui_connector defensive helpers (_safe_get, _safe_count)."""

import pytest
from unittest.mock import MagicMock, PropertyMock

from hana_connection_manager.sap_gui_connector import SAPGUIConnector, SAPGUISession


class TestSafeGet:
    """Tests for SAPGUIConnector._safe_get()."""

    def test_reads_normal_attribute(self):
        obj = MagicMock()
        obj.SystemName = "ABC"
        assert SAPGUIConnector._safe_get(obj, "SystemName") == "ABC"

    def test_returns_default_on_none_obj(self):
        assert SAPGUIConnector._safe_get(None, "SystemName") == ""

    def test_returns_default_on_none_obj_custom_default(self):
        assert SAPGUIConnector._safe_get(None, "SystemName", "N/A") == "N/A"

    def test_returns_default_when_attribute_raises(self):
        obj = MagicMock()
        type(obj).SystemName = PropertyMock(side_effect=Exception("COM error"))
        assert SAPGUIConnector._safe_get(obj, "SystemName") == ""

    def test_returns_default_when_attribute_is_none(self):
        obj = MagicMock()
        obj.Client = None
        assert SAPGUIConnector._safe_get(obj, "Client") == ""

    def test_coerces_int_to_str(self):
        obj = MagicMock()
        obj.SystemNumber = 42
        assert SAPGUIConnector._safe_get(obj, "SystemNumber") == "42"

    def test_returns_custom_default_on_error(self):
        class BadObj:
            @property
            def Foo(self):
                raise RuntimeError("COM dispatch error")
        obj = BadObj()
        assert SAPGUIConnector._safe_get(obj, "Foo", "fallback") == "fallback"


class TestSafeCount:
    """Tests for SAPGUIConnector._safe_count()."""

    def test_reads_normal_count(self):
        obj = MagicMock()
        obj.Children.Count = 3
        assert SAPGUIConnector._safe_count(obj) == 3

    def test_returns_zero_on_none(self):
        assert SAPGUIConnector._safe_count(None) == 0

    def test_returns_zero_when_children_raises(self):
        obj = MagicMock()
        type(obj).Children = PropertyMock(side_effect=Exception("COM error"))
        assert SAPGUIConnector._safe_count(obj) == 0

    def test_returns_zero_when_count_raises(self):
        obj = MagicMock()
        type(obj.Children).Count = PropertyMock(side_effect=Exception("access denied"))
        assert SAPGUIConnector._safe_count(obj) == 0


class TestDetectSessionsDefensive:
    """Tests that detect_sessions() handles edge cases gracefully."""

    def test_non_windows_returns_empty(self):
        """On non-Windows, detect_sessions returns [] without error."""
        connector = SAPGUIConnector()
        sessions = connector.detect_sessions()
        assert sessions == []

    def test_session_to_dict_shape_unchanged(self):
        """SAPGUISession.to_dict() returns expected keys."""
        session = SAPGUISession(
            system_id="ABC",
            client="100",
            user="ADMIN",
            session_id="/app/con[0]/ses[0]",
            connection_string="/H/10.0.0.1/S/3200",
            application_server="sapapp01",
            system_number="00",
            language="EN",
            transaction="SE80",
            is_active=True,
        )
        d = session.to_dict()
        expected_keys = {
            "session_id", "system_id", "client", "user",
            "application_server", "system_number", "language",
            "transaction", "connection_string", "is_active",
        }
        assert set(d.keys()) == expected_keys
        assert d["system_id"] == "ABC"
        assert d["session_id"] == "/app/con[0]/ses[0]"
        assert d["is_active"] is True

    def test_session_from_dict_roundtrip(self):
        """SAPGUISession.from_dict(to_dict()) roundtrips cleanly."""
        original = SAPGUISession(
            system_id="XYZ",
            client="200",
            user="TEST",
            session_id="/app/con[1]/ses[0]",
            connection_string="",
            application_server="host1",
            system_number="01",
            language="DE",
            transaction="SM21",
            is_active=True,
        )
        restored = SAPGUISession.from_dict(original.to_dict())
        assert restored.system_id == original.system_id
        assert restored.session_id == original.session_id
        assert restored.user == original.user
        assert restored.is_active == original.is_active


class TestProbeChildren:
    """Tests for SAPGUIConnector._probe_children()."""

    def test_finds_children_by_index(self):
        """Probes sequential indices and collects results."""
        child0 = MagicMock(name="ses0")
        child1 = MagicMock(name="ses1")

        obj = MagicMock()
        obj.Children = MagicMock(side_effect=[child0, child1, Exception("no more")])

        result = SAPGUIConnector._probe_children(obj, max_probe=5)
        assert len(result) == 2
        assert result[0] is child0
        assert result[1] is child1

    def test_returns_empty_when_first_index_fails(self):
        """Returns [] when even index 0 raises."""
        obj = MagicMock()
        obj.Children = MagicMock(side_effect=Exception("access denied"))
        result = SAPGUIConnector._probe_children(obj)
        assert result == []

    def test_stops_on_none(self):
        """Stops probing when None is returned."""
        child0 = MagicMock(name="ses0")
        obj = MagicMock()
        obj.Children = MagicMock(side_effect=[child0, None])
        result = SAPGUIConnector._probe_children(obj, max_probe=5)
        assert len(result) == 1

    def test_respects_max_probe_limit(self):
        """Never probes more than max_probe indices."""
        obj = MagicMock()
        # Always return a mock (infinite sessions)
        obj.Children = MagicMock(return_value=MagicMock())
        result = SAPGUIConnector._probe_children(obj, max_probe=3)
        assert len(result) == 3
