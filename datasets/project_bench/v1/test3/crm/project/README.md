# crm

A small sales CRM.

- Contacts are unique by email address. Addresses are compared without
  surrounding whitespace and regardless of letter case; adding a known address
  returns the existing contact and adds the new tags to it.
- A contact without an explicit company is linked to the company whose email
  domain matches.
- Deals move through the stages lead (10 %), qualified (25 %), proposal (50 %),
  negotiation (75 %) and end as won (100 %) or lost (0 %). Every move is
  recorded as a change from the old stage to the new one. Closed deals cannot
  move.
- Activities (call, email, meeting) produce reminders when they fall due.
- CSV files are uploaded into an import folder and imported from there.
  Columns: name, email, company, phone, tags (`;` separated).
- The forecast groups open deals by expected close month and weights each
  amount by its stage's probability.
