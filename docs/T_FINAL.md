# T-FINAL release candidate

Python package **5.1.0rc1** and Blender add-on **20.0.0** package the integrated feature set through PR #65. The input revision is [4217ea4913f1ac7be9e06c4362d282db13adeb30](https://github.com/vatrion360/GNM-Craniofacial-Approximation-Pipeline/commit/4217ea4913f1ac7be9e06c4362d282db13adeb30). For a case record, retain the candidate build's own commit and the SHA-256 of the artifact actually installed. The existing public tag v5.0.2 packaged software 5.0.0rc10 and add-on 19.0.0.

## Install or upgrade

| Artifact | Use |
| --- | --- |
| `gnm_cranio-5.1.0rc1.zip` | Install from Disk in Blender, enable GNM Scientific Markers, and verify version 20.0.0 in Preferences. |
| `gnm_craniofacial-5.1.0rc1-py3-none-any.whl` | Install in the external Python environment for the offline CLI. |
| `gnm_craniofacial-5.1.0rc1.tar.gz` | Source distribution with the build tools, example cases and T0.2 comparison snapshot. |

Back up the case .blend and exported landmarks before upgrading. Disable the previous add-on, install the new ZIP, reopen the case and confirm its model, marker positions and external Python path. The CLI continues to read earlier marker CSV formats. Blender exports case metadata in CSV v3. The existing case targets and opt-in fit settings carry forward. See [installation](INSTALL.md), [Romanian instructions](GHID_RO.md) and the [changelog](../CHANGELOG.md).

## Verify a candidate

Build from a clean checkout of the candidate commit using the development dependencies. Supply the separately verified official GNM model and an external Python environment as described in the installation guide.

```bash
python -m build
python tools/build_addon.py
python -m pytest -q
python scripts/run_baseline.py --suite examples/regression/suite.json --model "$GNM_MODEL_PATH" --compare baseline/5.0.0rc10
blender --background --factory-startup --python-exit-code 1 --python tools/blender_smoke.py
```

Set `GNM_EXTERNAL_PYTHON` for the external fitting and import checks. The committed T0.2 snapshot comes from the documented Linux environment. Keep that reference when checking the candidate. GitHub Actions runs the platform-specific Python, packaging and Blender integrations on Windows and Linux.

The builder prints the SHA-256 in the packaging job log. For a downloaded ZIP, run `Get-FileHash -Algorithm SHA256 .\gnm_cranio-5.1.0rc1.zip` on Windows or `sha256sum gnm_cranio-5.1.0rc1.zip` on Linux and compare with the digest supplied with that build. The builder fixes member timestamps, order and permissions to make rebuilds comparable with identical source bytes and compression tooling.

The acceptance checks cover installation, file compatibility, synthetic numerical regression and software behavior. Interactive review on the operator's workstation and validation against individual CT cases remain separate. This candidate has no assigned release DOI.
