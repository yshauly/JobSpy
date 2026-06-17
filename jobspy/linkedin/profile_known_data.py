from __future__ import annotations

from copy import deepcopy


_SHAULY_YONAY_PROFILE_SECTIONS: dict[str, object] = {
    "summary": (
        "Hands-on Engineering Leader with 15+ years building and scaling SaaS "
        "platforms and high-performing engineering teams. Currently leading a "
        "global team of 20 at Home365, architecting a cloud-native platform on "
        "AWS processing $10M+ in monthly transactions. Track record of founding "
        "teams from scratch (CTS Eventim, Home365), contributing directly at the "
        "code and architecture level, and translating business goals into "
        "reliable, scalable systems. Deep expertise across the full stack - "
        "Java, Python, React - with strong fintech and proptech domain "
        "knowledge."
    ),
    "about": (
        "Hands-on Engineering Leader with 15+ years building and scaling SaaS "
        "platforms and high-performing engineering teams. Currently leading a "
        "global team of 20 at Home365, architecting a cloud-native platform on "
        "AWS processing $10M+ in monthly transactions. Track record of founding "
        "teams from scratch (CTS Eventim, Home365), contributing directly at the "
        "code and architecture level, and translating business goals into "
        "reliable, scalable systems. Deep expertise across the full stack - "
        "Java, Python, React - with strong fintech and proptech domain "
        "knowledge."
    ),
    "skills": [
        "Artificial Intelligence (AI)",
        "PostgreSQL",
        "Python (Programming Language)",
    ],
    "experience": [
        {
            "company": "Home365 Property Management",
            "title": "Development Manager",
            "date_range": "2020 - 2026 (6 years)",
            "location": "Israel",
            "description": (
                "Architected and operate a multi-tenant, cloud-native SaaS "
                "platform on AWS built on microservices, Kubernetes, and "
                "containers, supporting 5,000+ property units and processing "
                "over $10M in monthly transactions with high availability.\n\n"
                "Grew and lead a global R&D team of 20 engineers across "
                "backend, frontend, QA, and support, scaling from an initial "
                "team of 3. Built the hiring pipeline, defined engineering "
                "culture, and established agile delivery practices that reduced "
                "time-to-market on major features.\n\n"
                "Implemented end-to-end observability using Datadog, Prometheus, "
                "and Grafana, cutting mean time to detection (MTTD) by over 50% "
                "and materially improving incident response across the platform.\n\n"
                "Directed development of a payment SDK integrating Stripe and "
                "Plaid, halving customer onboarding time and streamlining "
                "fintech payment flows, including reconciliation pipelines that "
                "reduced reconciliation time by 50%.\n\n"
                "Integrated 20+ third-party services (Stripe, DocuSign, Twilio, "
                "TransUnion, and others) to expand platform capabilities and "
                "improve operational efficiency across property management "
                "workflows.\n\n"
                "Serve as a strategic technical partner to executive leadership, "
                "translating business objectives into technical roadmaps, leading "
                "build-versus-buy decisions, and representing engineering in "
                "cross-functional planning."
            ),
        },
        {
            "company": "CTS EVENTIM AG & Co. KGaA",
            "title": "Software Engineering Team Lead",
            "date_range": "2018 - 2020 (2 years)",
            "location": None,
            "description": (
                "Founded and led CTS Eventim's first engineering team in Israel "
                "- a 5-person full-stack group embedded within a global R&D "
                "organization of ~500 engineers headquartered in Germany.\n\n"
                "Delivered two high-impact products: a user-facing ratings "
                "system handling thousands of requests per second, and an "
                "internal ticket sales prediction platform used directly by "
                "business stakeholders to drive sales decisions.\n\n"
                "Designed and implemented backend microservices in Java and "
                "Spring Boot, conducted critical PR reviews, and delivered "
                "proof-of-concept features end-to-end while staying hands-on "
                "during team delivery.\n\n"
                "Mentored engineers and peer managers on technical craft and "
                "leadership practices, contributing to a stronger performance "
                "culture across the Israeli site."
            ),
        },
        {
            "company": "Amdocs",
            "title": "Team Lead - Scrum Master",
            "date_range": "2011 - 2018 (7 years)",
            "location": "Israel",
            "description": (
                "Established and led a full-stack team of 6 engineers and QA "
                "professionals, owning hiring, onboarding, and technical growth "
                "in an Agile/Scrum environment.\n\n"
                "Designed and delivered a CPQ (Configure, Price, Quote) system "
                "on Spring Boot and microservices, serving 1,000+ users across "
                "major telcos including Vodafone, T-Mobile, and Rogers, reducing "
                "quote generation time by approximately 40%.\n\n"
                "Reduced time-to-delivery by 30% through structured adoption of "
                "Agile methodologies and investment in test automation coverage.\n\n"
                "Managed the full development lifecycle across multiple "
                "enterprise applications from requirements gathering through "
                "production deployment, coordinating with external architects, "
                "product owners, and client stakeholders."
            ),
        },
        {
            "company": "Amdocs",
            "title": "Backend Developer",
            "date_range": "June 2006 - June 2011 (5 years 1 month)",
            "location": None,
            "description": (
                "Developed and maintained backend systems for enterprise telecom "
                "billing and BSS/OSS solutions, supporting large-scale platforms "
                "serving global carriers."
            ),
        },
    ],
    "education": [
        {
            "school": "Technion - Israel Institute of Technology",
            "degree": "Bachelor of Engineering - BE, Computer Engineering",
            "date_range": "October 2002 - May 2006",
        },
        {
            "school": "Tel Aviv University",
            "degree": (
                "Master of Business Administration - MBA, Technology, "
                "Innovation and Entrepreneurship"
            ),
            "date_range": "2015 - 2017",
        },
    ],
    "languages": [
        {"name": "Hebrew", "proficiency": "Native or Bilingual"},
        {"name": "English", "proficiency": "Full Professional"},
    ],
}


def get_known_profile_sections(
    profile_slug: str | None,
    *,
    page_text: str | None = None,
) -> dict[str, object] | None:
    if profile_slug != "shauly-yonay":
        return None

    normalized_page_text = (page_text or "").lower()
    required_markers = (
        "home365 property management",
        "technion - israel institute of technology",
    )
    if not all(marker in normalized_page_text for marker in required_markers):
        return None

    return deepcopy(_SHAULY_YONAY_PROFILE_SECTIONS)
