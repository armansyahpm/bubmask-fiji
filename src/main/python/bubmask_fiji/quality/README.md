# Quality Layer

Responsible for input preflight metrics such as saturation, focus proxy,
illumination nonuniformity, missing calibration, and field-of-view confidence.

Implemented module:

- `scoring.py`

The quality layer converts raw detections into measurement statuses:

| Status | Meaning |
|---|---|
| `accepted_bubble` | Included in histogram-ready outputs. |
| `review_bubble` | Bubble-like, but blurred, saturated, border-touching, or weakly contrasted. |
| `rejected_nonbubble` | Fails hard size/geometry rules and should not be counted as a bubble. |

Current diagnostic fields include focus score, boundary-gradient score,
annular contrast, circularity, solidity, eccentricity, and
`accepted_for_histogram`.
