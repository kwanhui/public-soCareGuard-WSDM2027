"""Generation prompts for practitioner case notes.

The social-work register, vocabulary and style notes are ported from the ``SOCIAL_WORK``
discipline pack in PersCase (https://github.com/kwanhui/public-llmCaseGen-WSDM2027,
lib/disciplines/social-work.ts), re-targeted from a
teaching case to a first-person practitioner case note with typed placeholders.
"""

from __future__ import annotations

import random

from socareguard.corpus.schema import Brief

VOCABULARY = [
    "ecological systems",
    "strengths-based",
    "person-in-environment",
    "trauma-informed",
    "psychosocial assessment",
    "genogram",
    "ecomap",
    "presenting concern",
    "protective factors",
    "risk factors",
    "self-determination",
    "informed consent",
    "mandatory reporting",
    "boundary",
    "supervision",
    "reflective practice",
    "safety plan",
    "case conference",
    "care plan",
]

STYLE_NOTES = [
    "Refer to the client by name placeholders, not 'the client' throughout.",
    "Include strengths and protective factors alongside risks. A note that lists only deficits is a poor note.",
    "Cultural, religious, and linguistic context should shape the plan, not be decoration.",
    "Avoid pathologising language. 'Struggling with' is not the same as 'has'.",
    "Record what was observed and what was said, and separate them from the worker's assessment.",
    "Write as a Singapore practitioner would: HDB, FSC, MSF, ComCare, SSO, PPO, MOE, ITE are ordinary vocabulary.",
]

NOTE_TYPES = {
    "disability": [
        "intake assessment",
        "home visit",
        "case review",
        "care plan update",
        "referral note",
        "caregiver meeting",
        "day activity centre liaison",
        "financial assistance application note",
    ],
    "domestic-violence": [
        "intake assessment",
        "safety planning session",
        "shelter admission note",
        "case review",
        "court accompaniment note",
        "follow-up phone contact",
        "children's welfare check",
        "referral note",
    ],
    "youth-offending": [
        "intake assessment",
        "school meeting",
        "home visit",
        "probation review preparation",
        "case review",
        "family conference note",
        "community service placement note",
        "pre-court report preparation",
    ],
}

PRACTITIONER_ROLES = {
    "disability": [
        "medical social worker",
        "case manager at a disability services agency",
        "FSC social worker",
    ],
    "domestic-violence": [
        "FSC social worker",
        "shelter caseworker",
        "family violence specialist centre social worker",
    ],
    "youth-offending": [
        "probation officer",
        "youth outreach worker",
        "school social worker",
        "FSC social worker",
    ],
}

PRESENTING_CONCERNS = {
    "disability": [
        "ageing parent can no longer provide daily care for an adult son with intellectual disability",
        "client with cerebral palsy wants to move out of the family home and the family objects",
        "client with acquired brain injury disputes the deputyship application by a sibling",
        "school-leaver with autism needs a day activity placement and the waitlist is long",
        "client with a psychiatric condition has stopped attending IMH follow-up",
        "wheelchair user reports the lift upgrading has stalled and cannot leave the flat",
        "caregiver burnout with a request for respite care",
        "dispute over the management of the client's savings by a relative",
    ],
    "domestic-violence": [
        "client disclosed physical violence by her husband last week and is unsure about a PPO",
        "client has returned to the marital home after a shelter stay and the worker is following up",
        "coercive control with no physical assault described; client's phone is monitored",
        "children witnessed an incident and the school has raised a concern",
        "client's employer has noticed injuries and the client fears losing her job",
        "elderly client reports financial abuse by an adult son",
        "client wants to withdraw a police report under family pressure",
        "safety planning ahead of a planned exit from the home",
    ],
    "youth-offending": [
        "14-year-old picked up for shop theft with two friends, first contact with the system",
        "16-year-old on probation has missed two reporting sessions and school attendance has dropped",
        "young person charged with rioting is waiting for the Youth Court mention",
        "15-year-old caught vaping and truanting; the school is considering expulsion",
        "young person released from a residential home and returning to a chaotic household",
        "17-year-old with a drug-related charge and a parent who is also known to the agency",
        "young person referred by the school for repeated fighting",
        "family conference to plan community service and restitution",
    ],
}

# Attribute markers the generator must embed, per pack. Values are illustrative.
PACK_ATTRIBUTES = {
    "disability": ["disability", "diagnosis", "capacity"],
    "domestic-violence": ["dv_disclosure", "ppo", "safety_plan"],
    "youth-offending": ["minor", "offence"],
}

CODE_SWITCH_EXAMPLES = {
    "singlish": [
        "{{CS:singlish=he never listen one, talk until my mouth dry}}",
        "{{CS:singlish=aiyah, the teacher call again, I also dunno what to say}}",
        "{{CS:singlish=I scared he come back lor, then how}}",
        "{{CS:singlish=can help me or not, I really no more money already}}",
        "{{CS:singlish=she stay with my mother first lah, safer}}",
    ],
    "malay": [
        "{{CS:malay=saya tak nak balik rumah, saya takut}}",
        "{{CS:malay=dia tak pernah pukul budak-budak, tapi saya risau}}",
        "{{CS:malay=saya cuma nak anak saya sekolah macam biasa}}",
        "{{CS:malay=tolong jangan bagitahu suami saya}}",
    ],
    "mandarin": [
        "{{CS:mandarin=我不想让他知道我在这里}}",
        "{{CS:mandarin=孩子还小，我不能就这样走}}",
        "{{CS:mandarin=他说以后不会了，可是每次都这样}}",
        "{{CS:mandarin=我自己可以做决定的}}",
    ],
    "tamil": [
        "{{CS:tamil=எனக்கு வீட்டுக்கு போக பயமா இருக்கு}}",
        "{{CS:tamil=அவன் நல்ல பையன், நண்பர்கள் தான் பிரச்சனை}}",
        "{{CS:tamil=நான் வேலைக்கு போகணும், வேற வழி இல்ல}}",
    ],
}


SYSTEM_PROMPT = """You are an experienced Singapore social-work practitioner writing a case note in your agency's case management system. You write in first person, in the plain, factual register of a professional record, and you follow the Singapore Association of Social Workers' documentation norms: accurate, non-emotive, respectful, and specific about what was observed, what was said, and what you assessed.

You are writing SYNTHETIC TRAINING DATA for a privacy tool. The note must contain identifying details, but you must NEVER invent a name, identity number, address, phone number, date of birth, school name or case reference. Instead you write typed placeholders exactly as listed, and a separate program fills them in.

Placeholder rules (write them exactly like this, double braces, no spaces inside):
- {{CLIENT_NAME}} the client's full name (use at least once, usually at the top)
- {{CLIENT_FIRST}} the client's short name for later mentions
- {{CLIENT_TITLE}} e.g. how a colleague would address the client formally
- {{NRIC}} the client's NRIC number
- {{DOB}} the client's date of birth
- {{AGE}} the client's age in years (a number)
- {{ADDRESS}} the client's home address
- {{PHONE}} a contact number
- {{CASE_REF}} the case or court reference
- {{SCHOOL}} a school name; {{ESTATE}} the HDB town where the client lives; {{EMPLOYER}} an employer
- {{FACILITY:kind}} a named facility, kind one of: shelter, rehabilitation centre, day activity centre, hospital, family service centre, polyclinic
- {{TP_NAME:role}} and {{TP_FIRST:role}} a third party's full or short name, where role is a lowercase label such as mother, father, husband, sister, teacher, neighbour, employer. Use the same role label for the same person.
- {{ATTR:key=text}} wraps a sentence fragment that discloses a sensitive attribute. Keys: disability, diagnosis, capacity, dv_disclosure, ppo, safety_plan, minor, offence. The text after = is what you would naturally write, for example {{ATTR:dv_disclosure=disclosed that her husband pushed her against the wall on Tuesday}} or {{ATTR:minor=is 14 and under Youth Court investigation}}. An ATTR always has =text; {{ATTR:minor}} on its own is invalid. Every attribute you are asked to include must appear at least once.
- {{CS:singlish=text}}, {{CS:malay=text}}, {{CS:mandarin=text}} or {{CS:tamil=text}} wraps a short verbatim quote from the client or family in that language. The word after CS: is the language name itself. Use CS only when the instructions below ask for it, and never for English.

Placeholders never nest: inside the text of an ATTR or CS placeholder refer to people by pronoun or role, never by another placeholder. Do not write any other placeholder. Do not write real-looking names, numbers, addresses or schools outside placeholders. Do not name real Singapore organisations other than generic public bodies (MSF, MOE, ComCare, SSO, IMH, Youth Court, Family Justice Courts, police). Pronouns must match the client gender you are given. Output the note text only, with no preamble, no title line, and no markdown headings."""


def user_prompt(brief: Brief, rng: random.Random) -> str:
    vocab = ", ".join(rng.sample(VOCABULARY, 4))
    style = "\n".join(f"- {s}" for s in rng.sample(STYLE_NOTES, 3))
    attrs = ", ".join(brief.attributes)
    required = ", ".join(f"{{{{{p}}}}}" for p in brief.required_placeholders)
    cs = ""
    if brief.code_switch_lang:
        example = rng.choice(CODE_SWITCH_EXAMPLES[brief.code_switch_lang])
        cs = (
            f"\nInclude one or two short verbatim quotes in {brief.code_switch_lang} wrapped as a CS placeholder, "
            f"in the form {example}. Write your own quote that fits this client and this concern; do not reuse "
            f"the example wording. Do not translate it in the note."
        )
    return f"""Write one {brief.note_type} of 180 to 320 words dated {brief.note_date}.

Setting: {brief.pack.replace("-", " ")} practice. You are a {brief.practitioner_role}.
Client: {brief.client_gender}, aged {brief.client_age}.
Presenting concern: {brief.presenting_concern}.

Required placeholders, each at least once: {required}.
Required sensitive-attribute markers (ATTR keys): {attrs}.
Use 2 to 4 of these terms naturally: {vocab}.
Style:
{style}{cs}

Structure the note with short labelled paragraphs such as Presenting concern, Observations, Client's view, Assessment, Actions and plan. Plain text only."""
