import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from homebot.session.manager import SessionManager


class SessionManagerTest(unittest.TestCase):
    def test_deleted_session_is_not_restored_by_late_save(self) -> None:
        with TemporaryDirectory() as workspace:
            manager = SessionManager(Path(workspace))
            session = manager.get_or_create("voice:activation")
            session.add_message("user", "设置闹钟")
            manager.save(session)

            manager.delete_session(session.key)
            manager.save(session)

            self.assertIsNone(manager.read_session_file(session.key))


if __name__ == "__main__":
    unittest.main()
