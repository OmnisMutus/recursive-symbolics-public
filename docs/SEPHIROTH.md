# The Sephiroth: names and spellings

Support for the reader. The code reads a Sephirah written either way, in English or in Hebrew, but it always
answers with the English name, because not everyone reads Hebrew.

Each name is an English spelling of a Hebrew word, and English spells Hebrew more than one way. The Golden Dawn
wrote Kether and Tiphareth; modern romanisation writes Keter and Tiferet. This repository uses both, so the code
defines each Sephirah once, in `SEPHIROTH` in [symbolics/address.py](../symbolics/address.py), with every spelling
it knows, and `HEBREW_SPELLINGS` beside it gives the Hebrew word for each. Vowel points are ignored, so גְּבוּרָה
reads as גבורה. The identity check in `symbolics/ethics.py` reads both lists from there, so
"Anger is Gevurah." and "Anger is גבורה." are seen as the same claim as "Anger is Geburah.".

| Name in the code | Other spellings | Hebrew | The word means |
|---|---|---|---|
| Kether | Keter | כתר | crown |
| Chokmah | Chochmah, Chokhmah, Hokhmah, Hokmah | חכמה | wisdom |
| Binah | Bina | בינה | understanding |
| Chesed | Hesed, Khesed | חסד | loving-kindness, mercy |
| Geburah | Gevurah, Gebura, Gevura | גבורה | strength, severity |
| Tiphareth | Tifereth, Tiferet, Tiphereth, Tipheret | תפארת | beauty |
| Netzach | Netsach, Nezach | נצח | victory, endurance |
| Hod | | הוד | splendour |
| Yesod | Jesod, Iesod | יסוד | foundation |
| Malkuth | Malchut, Malkhut, Malchuth | מלכות | kingdom |
| Daath | Da'ath, Da’ath, Da'at, Daat | דעת | knowledge |

Daath comes last: it is drawn on some Trees but is not one of the ten. Hod has no other spelling: it is written
the same way in every romanisation.

Bina is also a given name, so "Bina is my sister." is read as an identity claim. The check matches words, not
meaning, and it errs toward asking for a lens rather than missing a claim.

"The word means" is the dictionary sense of the Hebrew word, nothing more. What a Sephirah stands for is a
reading inside one tradition, and this engine never says what a person "is" (see [ETHICS.md](ETHICS.md)).

To add a spelling, add it to its row in `SEPHIROTH` (or `HEBREW_SPELLINGS`) and to this table.
