import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("shortcut", ROOT / "tools/install_shortcut.py")
shortcut = importlib.util.module_from_spec(spec)
spec.loader.exec_module(shortcut)


class ShortcutTests(unittest.TestCase):
    def test_shift_uses_lowercase_key_and_preserves_existing_shortcuts(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "custom"
            existing = shortcut.entry(["Ctrl"], "space", "/example/launcher").replace(
                shortcut.DESC, "launcher")
            path.write_text("{\n" + existing + "}\n")
            with patch.object(shortcut, "PATH", str(path)), \
                    patch("sys.argv", ["install_shortcut.py", "--key", "I"]):
                shortcut.main()
                shortcut.main()
            text = path.read_text()
            self.assertIn(existing, text)
            self.assertIn('key: "i"', text)
            self.assertNotIn('key: "I"', text)
            self.assertEqual(text.count('description: Some("floor796 toggle")'), 1)

    def test_default_command_uses_this_checkout(self):
        self.assertIn(str(ROOT / "tools/ctl.py"), shortcut.DEFAULT_CMD)


if __name__ == "__main__":
    unittest.main()
