"""Task tray-03: the Windows named mutex behind the single-instance guard."""

import os
import unittest
import uuid

from quoroomtray.shell_settings import INSTANCE_MUTEX_NAME

if os.name == "nt":
    from quoroomtray.named_mutex import claim_named_mutex


def unique_name() -> str:
    return f"Local\\QuoroomTrayTest-{uuid.uuid4()}"


class SessionScopeTests(unittest.TestCase):
    def test_the_tray_mutex_is_per_logon_session_not_global(self):
        self.assertTrue(INSTANCE_MUTEX_NAME.startswith("Local\\"))

    def test_the_tray_mutex_name_has_exactly_one_namespace_separator(self):
        self.assertEqual(1, INSTANCE_MUTEX_NAME.count("\\"))


@unittest.skipUnless(os.name == "nt", "named mutexes are a Windows facility")
class NamedMutexTests(unittest.TestCase):
    def claim(self, name):
        mutex = claim_named_mutex(name)
        if mutex is not None:
            self.addCleanup(mutex.close)
        return mutex

    def test_the_first_claim_succeeds(self):
        self.assertIsNotNone(self.claim(unique_name()))

    def test_a_second_claim_of_the_same_name_is_refused(self):
        name = unique_name()
        self.claim(name)

        self.assertIsNone(self.claim(name))

    def test_a_refused_claim_does_not_release_the_first_one(self):
        name = unique_name()
        self.claim(name)
        self.claim(name)

        self.assertIsNone(self.claim(name))

    def test_another_name_is_independent(self):
        self.claim(unique_name())

        self.assertIsNotNone(self.claim(unique_name()))

    def test_the_name_is_free_again_after_the_holder_closes(self):
        name = unique_name()
        first = self.claim(name)

        first.close()

        self.assertIsNotNone(self.claim(name))

    def test_closing_twice_is_harmless(self):
        first = self.claim(unique_name())

        first.close()
        first.close()


if __name__ == "__main__":
    unittest.main()
