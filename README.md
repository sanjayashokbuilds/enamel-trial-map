# Enamel Trial Map

Every registered clinical trial on enamel repair (remineralisation, erosion, white-spot lesions, early caries) from ClinicalTrials.gov, sorted by who runs them, what they test and how the trials are designed.

I built this to answer three questions for an early-stage enamel regeneration company:

1. Which oral-care companies are actually testing alternatives to fluoride?
2. What does a typical enamel trial look like (size, length, endpoints, sites)?
3. Who else is in the clinic with a protein or biomimetic active?

## What I found

**838 enamel trials, 1,220 studies screened.** Industry sponsors only a small share of them. Since 2016 there are about 38 company-run trials against roughly 590 from universities and hospitals.

**The big brands barely test fluoride alternatives.** Since 2016:

| Company | Enamel trials | Testing a non-fluoride active |
|---|---|---|
| Colgate-Palmolive | 7 | 2 (both arginine, Colgate's own active) |
| Procter & Gamble | 5 | 2 (arginine) |
| Haleon (ex-GSK Consumer) | 4 | 1 |
| Church & Dwight | 3 | 0 |
| Unilever | 1 | 0 |

The companies that do test alternatives are small specialists: Dr. Wolff (hydroxyapatite), Mondelez's Trident gum (CPP-ACP) and Mintech-Bio.

**The closest competitor is already in the clinic.** Mintech-Bio (UK, built on research from Queen Mary University of London) is testing Epinamel, a protein-based gel that regrows enamel. The trial ([NCT07730359](https://clinicaltrials.gov/study/NCT07730359)) has these details:
- **Design:** split-mouth, with Epinamel against Curodont Repair.
- **Size:** 20 people.
- **Timing:** started July 2026, with completion estimated for January 2027.

**A typical industry trial for a new enamel active is small and fast.** Industry in-situ trials (volunteers wear enamel blocks in a mouth appliance) look like this:
- **Size:** median of 32 people (IQR 17–53).
- **Length:** about 3 months.
- **Primary endpoint:** surface microhardness, followed by mineral loss.

Full clinical trials run larger and longer: a median of 57 people over 16 months, scored on white-spot or ICDAS measures.

**The big brands run their trials at a handful of US sites.** These are the Oral Health Research Institute in Indianapolis, Therametric Technologies in Noblesville, and the companies' own sites in Cincinnati and Indianapolis.

**Most biomimetic research comes from universities.** There are 119 trials of peptide, protein, hydroxyapatite, P11-4 or bioactive glass actives:
- **Who runs them:** Egyptian dental schools run the most (Cairo 14, plus Mansoura, Al-Azhar, Ain Shams and Tanta), followed by the University of Pavia with 7.
- **Why that matters:** these groups already know how to run this kind of trial.

**Non-fluoride actives' share of trials has stayed steady.** It rose from 19% of trials in 2005–09 to about 25–29% since 2010.

## How it works

`enamel_trials.py` runs 20 searches against the ClinicalTrials.gov API (no key needed), then filters the results to enamel trials. It then tags each trial with:
- **Sponsor:** big oral-care brands are grouped under one name, and contract research organisations are excluded from the company ranking.
- **Active:** fluoride, stannous, arginine, hydroxyapatite, CPP-ACP, P11-4, other peptides, bioactive glass and so on.
- **Trial model:** in situ or clinical.
- **Primary endpoint.**

Classification rules:
- Stannous fluoride and silver diamine fluoride count as fluoride.
- Chalk/PCC toothpaste bases don't count as actives.
- Every tag saves the text it matched, so any call can be checked.

```
python3 enamel_trials.py
```

Outputs in `output/`:
- `trials.csv`: every trial with its tags and the evidence for each.
- `companies.csv`: the company ranking.
- `design_benchmarks.csv`: sample size, length and endpoints by trial type.
- `biomimetic_competitors.csv`: protein, peptide and biomimetic trials.
- `report.md`: the summary.

## Limits

- **Industry is undercounted.** Cosmetic toothpaste studies often aren't registered, so a company's real testing will be larger than what shows here.
- **Some tags will be wrong.** Tagging is pattern matching on registry text, so a few trials will be mislabelled; the evidence column shows why each tag was given.
- **Recent years are partial.** Start dates are as registered, and the 2025–29 bucket is still filling up.

Sanjay Ashok, UCL Economics
