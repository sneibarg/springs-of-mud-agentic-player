import unittest

from tests.live_session import QUIT_PHRASE, require_live_play


class TestLiveLogon(unittest.TestCase):
    def test_springs_of_mud_logs_on_the_low_level_character(self):
        play = require_live_play(self)
        try:
            character = play.character
            higher = [
                other.name
                for other in play.account.auth.player_character_list
                if other.level is not None and other.level > character.level
            ]
            self.assertTrue(higher)
            score = play.exchange("score")
            sheet = "\n".join(score)
            self.assertIn(f"You are {character.name} ", sheet)
            self.assertIn(f"level {character.level},", sheet)
            farewell = play.quit()
            self.assertTrue(any(QUIT_PHRASE in line for line in farewell))
        finally:
            play.close()


if __name__ == "__main__":
    unittest.main()
