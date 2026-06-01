# Packaging Decision

Decision for the first engineering milestone: use **local jar deployment**.

Rationale:

- It lets the team prove the SciJava command and Python worker boundary before
  taking on update-site operations.
- It avoids modifying Fiji's upstream-style `pom.xml` while BubMask is still
  changing quickly.
- It keeps the trained model, Python environment, and validation assets under
  the BubMask team's control.

## Milestone packaging path

1. Build `bubmask-fiji` with Maven.
2. Copy the jar to `Fiji.app/plugins/UNSW/` or launch Fiji with the jar on the
   classpath.
3. Set `-Dbubmask.worker=/absolute/path/to/bubmask_worker.py` if the worker is
   not next to the working directory.
4. Run `Plugins > UNSW > BubMask Microbubble Sizing`.

## Production packaging path

After validation and model packaging stabilize, move to a dedicated Fiji update
site:

- `UNSW-BubMask`
- artifact: `edu.unsw.mining:bubmask-fiji`
- model package: separate versioned artifact or update-site payload
- Python environment: documented Conda environment or Appose-managed env

Only after a stable release should Fiji's distribution `pom.xml` consider a
runtime dependency on BubMask.
