# How the README demo was captured

The GIF shows one run of CleanYourAndroid on a disposable Android 16 emulator in [GitHub Actions run 45596163302](https://github.com/shiv-eshwar/cleanyourandroid/actions/runs/45596163302). [Original Android screenshot](../images/android-16-settings.png) · [Annotated still](../images/light-plan.png) · [Sanitized transcript](session.json)

| Step | Command | What was checked |
| --- | --- | --- |
| Preview | `plan --light` | The plan contained only the three animation settings. Developer options showed 1× for Window, 1× for Transition, and 0.5× for Animator duration. The stored values were `1.0`, `1.0`, and `null`. |
| Apply | `apply` with the digest of that plan | The CLI journal reported the changes. All three settings read back as 0.5 and the Android screen showed half-duration animations. |
| Restore | `restore` with the same journal | Each stored value matched its original, including an unset value for animator duration. Android again displayed 1×, 1×, and 0.5×. |

The capture ran after the emulator integration test. Here, `null` meant the animator-duration setting was absent; it did not tell us which scale the UI would display. That is why the capture includes both the stored values and the screen.

The right panel consists of pixels cropped from Android's own **Developer options** screen. The left panel typesets selected fields from the CLI's JSON so they remain legible in a README. The explicit emulator selector is omitted from the displayed commands; `$digest` stands for the actual approval digest. Each frame is held for reading. The GIF does not show real-time command duration or benchmark animation speed.

## Reproduce it

1. Run the repository's **CI** workflow with **Run workflow**. Only manual dispatch runs [the capture script](capture.py), and it refuses to run outside the named disposable emulator. No personal phone is involved.
2. Download the resulting `readme-demo` artifact. It contains three unedited Android screenshots and selected output. Raw audits, approval digests, and device identifiers are not exported. Artifacts expire after three days; a fresh dispatch produces a fresh capture.
3. From the repository root, render the screenshots and transcript:

   ```sh
   gh run download RUN_ID -n readme-demo -D .cyandroid/readme-demo
   uv run --no-project --with pillow python docs/demo/render.py .cyandroid/readme-demo docs/images
   ```

The renderer uses system fonts (Arial and Menlo on macOS, or DejaVu Sans and DejaVu Sans Mono on Linux). It writes a three-frame GIF and a still PNG of the applied state. The text-only walkthrough and still screenshot are available even when animation is disabled.
