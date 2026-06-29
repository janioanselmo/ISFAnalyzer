# Audit — ZIP folders, repeated filenames and Envelope overlay

Date: 2026-06-29  
Version: v0.4.2-zip-folders-envelope-overlay

## User requirement

The experiment uses resonant pulse captures from two folders: the first-pulse set contains 14 acquisitions and the final/eighth-pulse set contains 20 acquisitions. For paired analysis, the app must be able to use the first 14 acquisitions from each folder.

The user also asked whether files with the same names need to be renamed and requested the Envelope tab to show the calculated envelope on the main waveform/peak-selection graph while keeping the envelope summary item separated.

## Decisions

1. File renaming is not required when the dataset is loaded as a ZIP containing folders.
2. Internal ZIP paths are preserved, for example:
   - `1 Pulso (Primeiro)/T0000CH1.ISF`
   - `8 Pulso (Final)/T0000CH1.ISF`
3. If direct standalone uploads contain duplicate basenames, the app keeps them internally by appending a duplicate suffix. However, ZIP loading is preferred because browser uploads may not expose the original folder path for standalone files.
4. Per-folder standardization is enabled by default and uses the first common number of distinct `TXXXX` acquisition indices in each folder.
5. Envelope item 2 remains the interactive waveform/peak-selection graph. When at least two valid peaks are selected, the fitted upper envelope is drawn in red on this graph.
6. Envelope item 3 remains separate and is used only for numerical comparison, compact metrics and CSV export.

## Validation with the supplied `Resultados.zip`

The uploaded ZIP was inspected structurally:

| Folder | Distinct `TXXXX` acquisitions | ISF files |
|---|---:|---:|
| `1 Pulso (Primeiro)` | 14 | 28 |
| `8 Pulso (Final)` | 20 | 40 |

Common standardized count: **14 acquisitions per folder**.

With both CH1 and CH2 present, this means the standardized dataset uses up to **56 ISF files**: 14 acquisitions × 2 channels × 2 folders.

## Non-redundancy rule

- The main Envelope graph shows visual context, peak selection and the fitted envelope overlay.
- The separated envelope section keeps summary metrics such as tau, R², decay per period, half-life and CSV export.
- No power, impedance or V×I phase metrics were moved into Envelope; those remain exclusive to Potência.
