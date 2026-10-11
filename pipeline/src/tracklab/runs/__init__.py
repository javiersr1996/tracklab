"""P5, "The run that moves nobody": which off-ball runs displace the defence, measured on the
tracking and never on the provider's label.

The protocol is code (`protocol.py`) and is committed before any outcome is computed; the
held-out half opens only through `data.load_half`, which refuses while the protocol of HEAD
is not frozen or the tree is dirty. `placebo.py` counts placebo candidates and nothing else.
`probe.py` is the first death probe (task 49): the calibration half alone, and no effect per
subtype. `candidates.py` is the second (task 50): the effect of the probable subtypes with
its controls, the candidates, and the freeze it prepares.
"""
