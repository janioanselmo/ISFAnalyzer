# Audit - Raw lobe peak envelope refinement

Date: 2026-06-30
Version: 0.5.3-raw-lobe-peak-envelope

## Objective

Confirm and harden the Envelope workflow so the fitted envelope uses the true
upper crest of each damped sinusoidal lobe.

## User requirement

- The envelope must be fitted using the maximum peak of each damped/resonant
  sinusoidal lobe.
- `N = 3` remains the default number of final peaks.
- `N` remains configurable in the Streamlit interface.

## Implementation

The peak detector still uses a lightly smoothed signal to avoid selecting
nanosecond-scale acquisition noise. However, every detected crest is now refined
back to the measured waveform before being used for the envelope fit:

1. Detect robust upper-crest candidates on the smoothed waveform.
2. For each candidate, open a narrow lobe-centered search window.
3. Select the raw maximum sample inside that window.
4. Deduplicate candidates so only one upper crest remains per lobe/cycle.
5. Use the refined raw crest coordinates for the red envelope fit.

## Files changed

- `ensaisf/domain/envelope_analysis.py`
- `ensaisf/presentation/theme.py`
- `governance/CHANGELOG.md`

## Validation

- Static syntax validation with `python -m py_compile`.
- Logic inspection confirmed that `fit_exponential_envelope()` receives selected
  peak coordinates from the refined raw upper crests.

## Git commit suggestion

Refine envelope detection to use raw maxima of damped sinusoidal lobes
