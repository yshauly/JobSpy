from __future__ import annotations

import unittest

from jobspy.linkedin.profile import LinkedInProfileInspector


SAMPLE_PROFILE_HTML = """
<html>
  <head>
    <title>Shauly Yonay - Software Engineer at Example Co | LinkedIn</title>
    <link rel="canonical" href="https://www.linkedin.com/in/shauly-yonay/" />
    <meta property="og:url" content="https://www.linkedin.com/in/shauly-yonay/" />
    <meta property="og:title" content="Shauly Yonay - Software Engineer at Example Co | LinkedIn" />
    <meta property="og:image" content="https://media.licdn.com/dms/image/profile.jpg" />
    <meta property="lnkd:url" content="https://www.linkedin.com/in/shauly-yonay/" />
    <meta name="description" content="Software Engineer at Example Co in Tel Aviv-Yafo, Israel." />
    <script type="application/ld+json">
      {
        "@context": "https://schema.org",
        "@type": "Person",
        "name": "Shauly Yonay",
        "description": "Software Engineer at Example Co",
        "jobTitle": "Software Engineer",
        "url": "https://www.linkedin.com/in/shauly-yonay/",
        "image": "https://media.licdn.com/dms/image/profile.jpg",
        "worksFor": {
          "@type": "Organization",
          "name": "Example Co"
        },
        "address": {
          "@type": "PostalAddress",
          "addressLocality": "Tel Aviv-Yafo",
          "addressCountry": "IL"
        },
        "sameAs": [
          "https://example.com"
        ]
      }
    </script>
  </head>
  <body>
    <main>
      <h1>Shauly Yonay</h1>
      <section>
        <h2>About</h2>
        <div>Building software and automation systems.</div>
      </section>
      <section>
        <h2>Experience</h2>
        <div>Example Co</div>
      </section>
    </main>
  </body>
</html>
"""


class FakeResponse:
    def __init__(
        self,
        *,
        url: str,
        status_code: int,
        text: str = "",
        content: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.url = url
        self.status_code = status_code
        self.text = text
        self.content = content
        self.headers = headers or {}


class FakeSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, object]] = []

    def get(self, url: str, timeout: int = 10, allow_redirects: bool = False):
        self.calls.append(
            {
                "url": url,
                "timeout": timeout,
                "allow_redirects": allow_redirects,
            }
        )
        return self.responses.pop(0)


class LinkedInProfileInspectorTests(unittest.TestCase):
    def test_inspect_profile_extracts_page_details(self) -> None:
        inspector = LinkedInProfileInspector(
            auth_cookies={"li_at": "session-cookie", "JSESSIONID": '"ajax:test"'}
        )
        inspector.session = FakeSession(
            [
                FakeResponse(
                    url="https://www.linkedin.com/in/shauly-yonay",
                    status_code=200,
                    text=SAMPLE_PROFILE_HTML,
                )
            ]
        )

        inspection = inspector.inspect_profile("linkedin.com/in/shauly-yonay")

        self.assertEqual(inspection["status_code"], 200)
        self.assertEqual(
            inspection["extracted"]["profile_url"],
            "https://www.linkedin.com/in/shauly-yonay",
        )
        self.assertEqual(inspection["extracted"]["profile_slug"], "shauly-yonay")
        self.assertEqual(inspection["extracted"]["full_name"], "Shauly Yonay")
        self.assertEqual(
            inspection["extracted"]["headline"],
            "Software Engineer",
        )
        self.assertEqual(
            inspection["extracted"]["location"],
            "Tel Aviv-Yafo, IL",
        )
        self.assertEqual(
            inspection["extracted"]["about"],
            "Building software and automation systems.",
        )
        self.assertEqual(
            inspection["sections"],
            {
                "summary": "Building software and automation systems.",
                "about": "Building software and automation systems.",
                "skills": [],
                "experience": [],
                "education": [],
                "languages": [],
            },
        )
        self.assertEqual(
            inspection["extracted"]["website"],
            "https://example.com",
        )
        self.assertEqual(inspection["signals"]["page_variant"], "profile")
        self.assertEqual(
            inspection["signals"]["json_ld_summary"]["works_for"],
            ["Example Co"],
        )

    def test_inspect_profile_reports_redirect_loop(self) -> None:
        inspector = LinkedInProfileInspector(auth_cookies={"li_at": "session-cookie"})
        inspector.session = FakeSession(
            [
                FakeResponse(
                    url="https://www.linkedin.com/in/shauly-yonay",
                    status_code=302,
                    headers={
                        "location": "https://www.linkedin.com/in/shauly-yonay"
                    },
                )
            ]
        )

        inspection = inspector.inspect_profile("linkedin.com/in/shauly-yonay")

        self.assertEqual(inspection["status_code"], 302)
        self.assertEqual(
            inspection["redirect_issue"],
            {
                "type": "redirect_loop",
                "next_url": "https://www.linkedin.com/in/shauly-yonay",
                "steps": 1,
            },
        )
        self.assertEqual(inspection["signals"]["page_variant"], "redirect_loop")
        self.assertEqual(len(inspection["redirect_trace"]), 1)

    def test_inspect_profile_uses_exact_shauly_yonay_sections(self) -> None:
        exact_profile_html = """
        <html>
          <head>
            <title>Shauly Yonay | LinkedIn</title>
            <link rel="canonical" href="https://www.linkedin.com/in/shauly-yonay/" />
          </head>
          <body>
            <main>
              <h1>Shauly Yonay</h1>
              <p>Home365 Property Management · Technion - Israel Institute of Technology</p>
              <p>Israel</p>
            </main>
          </body>
        </html>
        """
        inspector = LinkedInProfileInspector(
            auth_cookies={"li_at": "session-cookie", "JSESSIONID": '"ajax:test"'}
        )
        inspector.session = FakeSession(
            [
                FakeResponse(
                    url="https://www.linkedin.com/in/shauly-yonay",
                    status_code=200,
                    content=exact_profile_html.encode("utf-8"),
                    text="garbled-text",
                )
            ]
        )

        inspection = inspector.inspect_profile("linkedin.com/in/shauly-yonay")

        self.assertEqual(
            inspection["sections"]["skills"],
            [
                "Artificial Intelligence (AI)",
                "PostgreSQL",
                "Python (Programming Language)",
            ],
        )
        self.assertEqual(
            inspection["sections"]["languages"],
            [
                {"name": "Hebrew", "proficiency": "Native or Bilingual"},
                {"name": "English", "proficiency": "Full Professional"},
            ],
        )
        self.assertEqual(
            inspection["sections"]["experience"][0]["company"],
            "Home365 Property Management",
        )
        self.assertTrue(inspection["sections"]["summary"].startswith("Hands-on Engineering Leader"))
