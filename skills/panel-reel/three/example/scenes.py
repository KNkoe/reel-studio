"""A starting point: copy into a project as scenes.py. Times are seconds on the edit's clock.

c(t) turns an edit time into a time inside the scene. Place things in picture pixels with
P(px, py, depth). In a SPLIT scene keep everything between rows 250 and 930.
"""
import pathlib

import kit as K
import props as Q
from kit import FLAG, ORANGE, SPLIT, WHITE, P, pop, scene
from props import label

Q.SHIELD_WORD = "SAFE"


@scene("idea", 0.0, 4.0, SPLIT)
def idea(c, length):
    Q.title(["THE IDEA"], c(0.2), row=335, size=100, colours=(ORANGE,))
    shield = Q.shield(2.8, 3.3, location=P(540, 700, 0))
    pop(shield, c(0.6), 0.6)
    K.bob(shield, 0.1, 1.6, 0, 0.2)
    for i, (px, word) in enumerate(((200, "Collect"), (880, "Compare"))):
        page = Q.document(1.7, 2.2, location=P(px, 700, 0.3), seed=i + 1, heading=FLAG if i else ORANGE)
        pop(page, c(1.2 + i * 0.4), 0.5)
        label(word, px, 962, 1.4 + i * 0.4, c, 46, WHITE, -1.2, 300)
