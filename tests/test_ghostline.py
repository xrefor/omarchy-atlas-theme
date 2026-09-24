from __future__ import annotations

import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "components/apps/ghostline"))

import ghostline_director as director
import ghostline_overlay as overlay


ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")


class VisualContractsTest(unittest.TestCase):
    def test_card_registry_is_consistent(self) -> None:
        scheduled = {kind for _, kind, _, _, _ in director.SCHEDULE}
        self.assertLessEqual(scheduled, overlay.CARDS.keys())
        self.assertEqual(overlay.CARDS.keys(), overlay.STYLE_FOR_KIND.keys())
        self.assertEqual(overlay.CARDS.keys(), director.CARD_SIZES.keys())
        self.assertLessEqual(set(overlay.STYLE_FOR_KIND.values()), overlay.VIEW_RENDERERS.keys())

    def test_equipment_cards_are_materially_larger(self) -> None:
        safe = (40, 40, 1800, 960)
        route_width, route_height = director.card_size("route", safe)
        pump_width, pump_height = director.card_size("pump", safe)
        inspection_width, inspection_height = director.card_size("inspection", safe)
        self.assertGreater(pump_width, route_width)
        self.assertGreater(pump_height, route_height)
        self.assertGreaterEqual(inspection_width, pump_width)
        self.assertGreaterEqual(inspection_height, pump_height)
        self.assertLessEqual(inspection_width, safe[2])
        self.assertLessEqual(inspection_height, safe[3])

    def test_pump_drawing_has_process_landmarks_and_animation(self) -> None:
        title, source, raw_fields = overlay.CARDS["pump"]
        fields = overlay.fields_as_pairs(raw_fields)
        first = "\n".join(overlay.pump_view("pump", "PUMP TRAIN", title, source, fields, 120, 0.0))
        second = "\n".join(overlay.pump_view("pump", "PUMP TRAIN", title, source, fields, 120, 0.2))
        plain = ANSI.sub("", first)
        for landmark in ("SUCTION", "IMPELLER", "DISCHARGE", "PROCESS FLOW"):
            self.assertIn(landmark, plain)
        self.assertNotEqual(first, second)
        self.assertLessEqual(max(map(len, plain.splitlines())), 120)

    def test_inspection_drawing_has_inline_tool_landmarks_and_animation(self) -> None:
        title, source, raw_fields = overlay.CARDS["inspection"]
        fields = overlay.fields_as_pairs(raw_fields)
        first = "\n".join(
            overlay.inspection_view("inspection", "ILI TOOL PASS", title, source, fields, 120, 0.0)
        )
        second = "\n".join(
            overlay.inspection_view("inspection", "ILI TOOL PASS", title, source, fields, 120, 0.25)
        )
        plain = ANSI.sub("", first)
        for landmark in ("PIPE WALL", "CUP", "SENSOR RING", "ODOMETER", "BATTERY"):
            self.assertIn(landmark, plain)
        self.assertNotEqual(first, second)
        self.assertLessEqual(max(map(len, plain.splitlines())), 120)


class DirectorLifecycleTest(unittest.TestCase):
    def test_logical_monitor_rect_honors_origin_scale_and_rotation(self) -> None:
        monitor = {
            "x": -1920,
            "y": 120,
            "width": 1080,
            "height": 1920,
            "scale": 1.5,
            "transform": 1,
            "reserved": [10, 20, 30, 40],
        }
        self.assertEqual(director.logical_monitor_rect(monitor), (-1868, 182, 1156, 576))

    def test_main_uses_private_owned_runtime_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state_dir = Path(directory) / "state"
            state_dir.mkdir(mode=0o700)
            argv = [
                "ghostline_director.py",
                "--workspace",
                "2",
                "--start",
                "0",
                "--state-dir",
                str(state_dir),
            ]
            with (
                mock.patch.object(sys, "argv", argv),
                mock.patch.object(director.signal, "signal"),
                mock.patch.object(director.Director, "run") as run,
            ):
                director.main()
            run.assert_called_once_with()
            self.assertFalse((state_dir / "director-2.pid").exists())

    def test_main_rejects_linked_or_shared_runtime_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            private = root / "private"
            private.mkdir(mode=0o700)
            linked = root / "linked"
            linked.symlink_to(private, target_is_directory=True)
            shared = root / "shared"
            shared.mkdir(mode=0o755)
            for state_dir in (linked, shared):
                argv = [
                    "ghostline_director.py",
                    "--workspace",
                    "2",
                    "--start",
                    "0",
                    "--state-dir",
                    str(state_dir),
                ]
                with self.subTest(state_dir=state_dir), mock.patch.object(sys, "argv", argv):
                    with self.assertRaisesRegex(SystemExit, "must be private and owned"):
                        director.main()

    def test_main_wall_presence_requires_owned_mapped_panel(self) -> None:
        clients = [
            {"class": "unrelated", "mapped": True, "workspace": {"id": 2}},
            {"class": "atlas-ghostline-core", "mapped": False, "workspace": {"id": 2}},
            {"class": "atlas-ghostline-core", "mapped": True, "workspace": {"id": 3}},
        ]
        self.assertFalse(director.main_wall_present(clients, 2))
        clients.append({"class": "atlas-ghostline-access", "mapped": True, "workspace": {"id": 2}})
        self.assertTrue(director.main_wall_present(clients, 2))

    def test_run_stops_and_cleans_up_when_wall_is_closed(self) -> None:
        instance = director.Director(2, 0.0, Path("."))
        with (
            mock.patch.object(director, "hypr_json", return_value=[]),
            mock.patch.object(instance, "spawn_card") as spawn,
            mock.patch.object(instance, "close_active_cards") as cleanup,
        ):
            instance.run()
        spawn.assert_not_called()
        cleanup.assert_called_once_with()

    def test_cleanup_revalidates_address_class_and_workspace(self) -> None:
        instance = director.Director(2, 0.0, Path("."))
        instance.active = {
            "atlas-ghostline-overlay-good": ("0x1", 10.0, (0, 0, 10, 10)),
            "atlas-ghostline-overlay-other": ("0x2", 10.0, (0, 0, 10, 10)),
        }
        clients = [
            {"address": "0x1", "class": "atlas-ghostline-overlay-good", "workspace": {"id": 2}},
            {"address": "0x2", "class": "atlas-ghostline-overlay-other", "workspace": {"id": 3}},
        ]
        with (
            mock.patch.object(director, "hypr_json", return_value=clients),
            mock.patch.object(director, "dispatch") as dispatch,
        ):
            instance.close_active_cards()
        dispatch.assert_called_once_with('hl.dsp.window.close({ window = "address:0x1" })')
        self.assertEqual(instance.active, {})


if __name__ == "__main__":
    unittest.main()
