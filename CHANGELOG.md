# Changelog

## v0.3.22-ringdown-tracker

- Replaced the envelope auto-selection logic with a ringdown-cycle tracker.
- The default mode now anchors on the dominant forced crest and tracks the next N natural upper crests cycle-by-cycle.
- Removed pre-trigger baseline markers from the candidate pool using adaptive noise gating.
- Kept valleys/minima out of the envelope candidate set.
- Kept manual click selection and multi-file overlay behavior unchanged.
