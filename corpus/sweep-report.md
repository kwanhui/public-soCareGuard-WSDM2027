# Spontaneous-entity sweep report

Detections by off-the-shelf detectors that do not overlap any gold span. Each is either a
spontaneous identifier the generator invented (a gold-span gap to fix) or a detector false
positive (no action). The audit checklist below is a fixed random sample for manual review.

- Notes swept: 300
- Notes with at least one candidate: 84 (28.0%)
- Candidates: 121
- By detector label: {"case reference": 2, "address": 9, "organization": 43, "NRP": 17, "person": 11, "LOCATION": 2, "PERSON": 27, "school": 9, "email": 1}

## Candidates

| note | span | text | label | detector | score |
|---|---|---|---|---|---|
| disability-000 | 1791-1803 | MSF casework | case reference | gliner | 0.54 |
| disability-001 | 919-927 | HDB flat | address | gliner | 0.63 |
| disability-002 | 1717-1738 | Family Service Centre | organization | gliner | 0.85 |
| disability-002 | 1909-1951 | Medical Social Worker, Disability Services | organization | gliner | 0.66 |
| disability-003 | 479-487 | Singlish | NRP | presidio | 0.85 |
| disability-003 | 743-749 | Mother | person | gliner | 0.63 |
| disability-007 | 1611-1615 | D.C. | LOCATION | presidio | 0.85 |
| disability-008 | 716-721 | Tamil | NRP | presidio | 0.85 |
| disability-008 | 822-827 | Tamil | NRP | presidio | 0.85 |
| disability-009 | 327-335 | HDB flat | address | gliner | 0.55 |
| disability-009 | 1683-1690 | FSC/MSF | organization | gliner | 0.53 |
| disability-015 | 1739-1759 | Community Healthcare | organization | gliner | 0.74 |
| disability-020 | 1764-1790 | SSO/Community Legal Clinic | organization | gliner | 0.87 |
| disability-022 | 1708-1715 | MSF/SSO | organization | gliner | 0.51 |
| disability-023 | 142-167 | day activity centre (DAC) | organization | gliner | 0.66 |
| disability-023 | 349-352 | DAC | organization | gliner | 0.92 |
| disability-023 | 512-520 | HDB flat | address | gliner | 0.91 |
| disability-023 | 1338-1345 | Liaised | PERSON | presidio | 0.85 |
| disability-023 | 1351-1354 | DAC | organization | gliner | 0.90 |
| disability-023 | 1594-1597 | DAC | organization | gliner | 0.89 |
| disability-023 | 1629-1640 | SSO/ComCare | organization | gliner | 0.52 |
| disability-025 | 295-303 | HDB flat | address | gliner | 0.60 |
| disability-025 | 1423-1429 | Ecomap | PERSON | presidio | 0.85 |
| disability-027 | 439-446 | Chinese | NRP | presidio | 0.85 |
| disability-030 | 1555-1566 | MSF/ComCare | organization | gliner | 0.87 |
| disability-031 | 1083-1089 | Ecomap | PERSON | presidio | 0.85 |
| disability-040 | 187-190 | Son | PERSON | presidio | 0.85 |
| disability-046 | 2105-2126 | MSF/Community Support | organization | gliner | 0.80 |
| disability-051 | 1885-1892 | FSC/MSF | organization | gliner | 0.83 |
| disability-055 | 257-260 | DAC | school | gliner | 0.70 |
| disability-055 | 1369-1372 | DAC | school | gliner | 0.62 |
| disability-055 | 1523-1526 | DAC | school | gliner | 0.60 |
| disability-056 | 1628-1635 | Liaised | PERSON | presidio | 0.85 |
| disability-059 | 420-426 | Speech | PERSON | presidio | 0.85 |
| disability-062 | 1883-1894 | MSF/ComCare | organization | gliner | 0.57 |
| disability-063 | 543-564 | Social Service Office | organization | gliner | 0.62 |
| disability-067 | 895-900 | Aiyah | PERSON | presidio | 0.85 |
| disability-069 | 414-420 | Speech | PERSON | presidio | 0.85 |
| disability-069 | 1374-1380 | Liaise | PERSON | presidio | 0.85 |
| disability-072 | 1739-1751 | Town Council | organization | gliner | 0.55 |
| disability-072 | 1840-1851 | SSO/ComCare | organization | gliner | 0.65 |
| disability-079 | 1405-1412 | Liaised | PERSON | presidio | 0.85 |
| disability-079 | 1687-1698 | MSF/ComCare | organization | gliner | 0.90 |
| disability-081 | 60-79 | Day Activity Centre | organization | gliner | 0.88 |
| disability-081 | 1516-1523 | Liaised | PERSON | presidio | 0.85 |
| disability-087 | 1675-1691 | HDB/Town Council | organization | gliner | 0.64 |
| disability-090 | 810-818 | Singlish | NRP | presidio | 0.85 |
| disability-092 | 262-270 | HDB flat | address | gliner | 0.66 |
| disability-092 | 1505-1512 | MSF/SSO | organization | gliner | 0.70 |
| disability-093 | 115-117 | GP | person | gliner | 0.86 |
| disability-093 | 1646-1648 | GP | person | gliner | 0.82 |
| disability-095 | 856-859 | Wah | PERSON | presidio | 0.85 |
| disability-097 | 171-190 | MOE transition team | organization | gliner | 0.85 |
| disability-098 | 1609-1620 | MSF/ComCare | organization | gliner | 0.69 |
| disability-099 | 1389-1405 | HDB Town Council | organization | gliner | 0.93 |
| disability-099 | 1634-1645 | SSO/ComCare | organization | gliner | 0.78 |
| domestic-violence-011 | 818-824 | Jangan | PERSON | presidio | 0.85 |
| domestic-violence-015 | 960-963 | Wah | PERSON | presidio | 0.85 |
| domestic-violence-016 | 289-295 | Client | person | gliner | 0.67 |
| domestic-violence-016 | 1093-1099 | Client | person | gliner | 0.61 |
| domestic-violence-022 | 302-311 | HDB block | address | gliner | 0.60 |
| domestic-violence-026 | 88-99 | FSC shelter | organization | gliner | 0.55 |
| domestic-violence-028 | 1270-1280 | Emphasised | PERSON | presidio | 0.85 |
| domestic-violence-028 | 1826-1837 | Case worker | case reference | gliner | 0.59 |
| domestic-violence-031 | 352-360 | HDB flat | address | gliner | 0.80 |
| domestic-violence-034 | 472-478 | Speech | PERSON | presidio | 0.85 |
| domestic-violence-037 | 134-144 | FSC office | organization | gliner | 0.83 |
| domestic-violence-039 | 230-236 | School | organization | gliner | 0.53 |
| domestic-violence-042 | 120-123 | FVS | organization | gliner | 0.77 |
| domestic-violence-044 | 62-68 | FEMALE | PERSON | presidio | 0.85 |
| domestic-violence-053 | 492-498 | School | school | gliner | 0.80 |
| domestic-violence-057 | 95-116 | Family Service Centre | organization | gliner | 0.97 |
| domestic-violence-061 | 341-346 | Child | PERSON | presidio | 0.85 |
| domestic-violence-062 | 38-44 | School | school | gliner | 0.75 |
| domestic-violence-062 | 137-170 | Family Violence Specialist Centre | organization | gliner | 0.89 |
| domestic-violence-066 | 658-663 | Tamil | LOCATION | presidio | 0.85 |
| domestic-violence-068 | 1705-1716 | MSF/ComCare | organization | gliner | 0.70 |
| domestic-violence-072 | 161-200 | family violence specialist centre (FSC) | organization | gliner | 0.86 |
| domestic-violence-073 | 1693-1700 | MOE SSW | PERSON | presidio | 0.85 |
| domestic-violence-075 | 1377-1389 | SSO by email | email | gliner | 0.56 |
| domestic-violence-077 | 88-96 | HDB flat | address | gliner | 0.57 |
| domestic-violence-083 | 94-106 | Family Court | organization | gliner | 0.84 |
| domestic-violence-083 | 290-298 | HDB flat | address | gliner | 0.57 |
| domestic-violence-086 | 90-100 | FSC office | organization | gliner | 0.92 |
| domestic-violence-089 | 94-98 | FVSC | NRP | presidio | 0.85 |
| domestic-violence-089 | 94-98 | FVSC | organization | gliner | 0.53 |
| domestic-violence-089 | 1532-1548 | SSO legal clinic | organization | gliner | 0.53 |
| domestic-violence-090 | 1593-1614 | Family Service Centre | organization | gliner | 0.56 |
| domestic-violence-097 | 370-373 | Tel | PERSON | presidio | 0.85 |
| domestic-violence-097 | 1596-1603 | MOE SSO | PERSON | presidio | 0.85 |
| domestic-violence-097 | 1596-1603 | MOE SSO | school | gliner | 0.61 |
| youth-offending-003 | 121-127 | School | school | gliner | 0.76 |
| youth-offending-003 | 252-258 | School | school | gliner | 0.64 |
| youth-offending-003 | 1460-1466 | School | school | gliner | 0.80 |
| youth-offending-003 | 1700-1706 | Mother | person | gliner | 0.54 |
| youth-offending-011 | 1246-1251 | Malay | NRP | presidio | 0.85 |
| youth-offending-014 | 1458-1469 | MSF/ComCare | organization | gliner | 0.52 |
| youth-offending-021 | 1774-1780 | Mother | person | gliner | 0.56 |
| youth-offending-022 | 730-738 | Singlish | NRP | presidio | 0.85 |
| youth-offending-022 | 851-859 | Singlish | NRP | presidio | 0.85 |
| youth-offending-024 | 1983-1990 | FSC/MSF | organization | gliner | 0.69 |
| youth-offending-025 | 1429-1434 | Malay | NRP | presidio | 0.85 |
| youth-offending-026 | 1015-1021 | Mother | person | gliner | 0.54 |
| youth-offending-026 | 1819-1826 | MSF/SSO | organization | gliner | 0.70 |
| youth-offending-027 | 460-466 | Mother | person | gliner | 0.87 |
| youth-offending-027 | 666-672 | Mother | person | gliner | 0.83 |
| youth-offending-032 | 907-915 | Singlish | NRP | presidio | 0.85 |
| youth-offending-039 | 1790-1796 | Liaise | PERSON | presidio | 0.85 |
| youth-offending-043 | 629-655 | Saya takut kalau dia terus | PERSON | presidio | 0.85 |
| youth-offending-061 | 1125-1130 | Malay | NRP | presidio | 0.85 |
| youth-offending-068 | 930-938 | Singlish | NRP | presidio | 0.85 |
| youth-offending-068 | 1177-1185 | Singlish | NRP | presidio | 0.85 |
| youth-offending-069 | 668-671 | Wah | PERSON | presidio | 0.85 |
| youth-offending-070 | 475-481 | Mother | person | gliner | 0.84 |
| youth-offending-070 | 1201-1207 | Muslim | NRP | presidio | 0.85 |
| youth-offending-071 | 1703-1710 | Liaised | PERSON | presidio | 0.85 |
| youth-offending-083 | 1373-1378 | Malay | NRP | presidio | 0.85 |
| youth-offending-083 | 1440-1445 | Malay | NRP | presidio | 0.85 |
| youth-offending-088 | 1575-1596 | Family Service Centre | organization | gliner | 0.57 |
| youth-offending-094 | 1660-1666 | Liaise | PERSON | presidio | 0.85 |
| youth-offending-099 | 1536-1542 | Liaise | PERSON | presidio | 0.85 |

## Manual audit checklist (30 notes, fixed seed)

- [ ] disability-003 (candidates above): read the full note and confirm every identifier is inside a gold span
- [ ] disability-015 (candidates above): read the full note and confirm every identifier is inside a gold span
- [ ] disability-019 (no candidates): read the full note and confirm every identifier is inside a gold span
- [ ] disability-021 (no candidates): read the full note and confirm every identifier is inside a gold span
- [ ] disability-024 (no candidates): read the full note and confirm every identifier is inside a gold span
- [ ] disability-029 (no candidates): read the full note and confirm every identifier is inside a gold span
- [ ] disability-042 (no candidates): read the full note and confirm every identifier is inside a gold span
- [ ] disability-049 (no candidates): read the full note and confirm every identifier is inside a gold span
- [ ] disability-053 (no candidates): read the full note and confirm every identifier is inside a gold span
- [ ] disability-063 (candidates above): read the full note and confirm every identifier is inside a gold span
- [ ] disability-065 (no candidates): read the full note and confirm every identifier is inside a gold span
- [ ] disability-084 (no candidates): read the full note and confirm every identifier is inside a gold span
- [ ] domestic-violence-006 (no candidates): read the full note and confirm every identifier is inside a gold span
- [ ] domestic-violence-008 (no candidates): read the full note and confirm every identifier is inside a gold span
- [ ] domestic-violence-011 (candidates above): read the full note and confirm every identifier is inside a gold span
- [ ] domestic-violence-014 (no candidates): read the full note and confirm every identifier is inside a gold span
- [ ] domestic-violence-016 (candidates above): read the full note and confirm every identifier is inside a gold span
- [ ] domestic-violence-038 (no candidates): read the full note and confirm every identifier is inside a gold span
- [ ] domestic-violence-049 (no candidates): read the full note and confirm every identifier is inside a gold span
- [ ] domestic-violence-052 (no candidates): read the full note and confirm every identifier is inside a gold span
- [ ] domestic-violence-061 (candidates above): read the full note and confirm every identifier is inside a gold span
- [ ] domestic-violence-069 (no candidates): read the full note and confirm every identifier is inside a gold span
- [ ] youth-offending-002 (no candidates): read the full note and confirm every identifier is inside a gold span
- [ ] youth-offending-016 (no candidates): read the full note and confirm every identifier is inside a gold span
- [ ] youth-offending-043 (candidates above): read the full note and confirm every identifier is inside a gold span
- [ ] youth-offending-062 (no candidates): read the full note and confirm every identifier is inside a gold span
- [ ] youth-offending-088 (candidates above): read the full note and confirm every identifier is inside a gold span
- [ ] youth-offending-089 (no candidates): read the full note and confirm every identifier is inside a gold span
- [ ] youth-offending-096 (no candidates): read the full note and confirm every identifier is inside a gold span
- [ ] youth-offending-097 (no candidates): read the full note and confirm every identifier is inside a gold span
