# Third-party components

The image builds [Carbonate](https://github.com/develonrails/carbonate) from pinned
commit `baa9818402e980208ac0041ea6544f3d4683d29d`, under its MIT license. The
project adds a CLI patch and two source files for machine-readable reads. The
upstream repository and its license remain available in the build-stage checkout.
The final image contains the compiled bridge; preserve its license notices before
distributing images publicly.

The Python adapter uses FastAPI, Uvicorn and icalendar. Recurrence expansion uses
[recurring-ical-events](https://pypi.org/project/recurring-ical-events/) 3.8.2,
licensed LGPL-3.0-or-later, installed as an independent Python dependency. Its
licensing obligations and those of transitive dependencies must be checked before
public distribution. Tailscale, Caddy, Go and Python container images have their
own licenses and notices.

This private project has not yet selected a license for its original source.
Publishing source privately is not a public licensing grant. Choose a license and
include the required dependency notices before a public release or distributed
prebuilt image. This project is unofficial and is not affiliated with Proton.
