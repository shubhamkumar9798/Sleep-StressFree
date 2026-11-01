# Research-gap analysis

**Project:** Stress estimation from consumer-wearable physiological data, built on the QoL_Stress dataset.
**Prepared:** November 2026.

This review was done with targeted web and database searches, mainly PubMed/PMC, publisher pages, arXiv, dblp and the PhysioNet dataset page. It is **not** a systematic review: no PRISMA protocol was followed and full texts were not screened for every result. Statements about what the literature does or does not contain are limited to the sources listed in Section 6.

---

## 1. Literature summary

Each entry gives the source, its dataset or signals, what it did, how it was evaluated, its main finding, and why it matters for this project.

### Reviews

**Vos et al., 2023** — *Int. J. Med. Inform.* [vos2023generalizable]
- **Data:** systematic review of 33 studies, mostly using the Empatica E4.
- **Method:** a systematic review of how well wearable stress models generalize.
- **Evaluation:** IJMEDI quality checklist.
- **Finding:** most studies use small, single datasets and generalize poorly. The authors call for larger, more diverse data and flag concerns about labelling and statistical power.
- **Relevance:** it motivates participant-independent evaluation and honest reporting of uncertainty.

**Schmidt et al., 2019** — *Sensors* [schmidt2019review]
- **Data:** a review of public datasets.
- **Method:** a review of wearable affect recognition.
- **Evaluation:** narrative.
- **Finding:** describes the standard processing chain and the datasets available.
- **Relevance:** background for the field.

**Giannakakis et al., 2022** (online 2019) — *IEEE TAC* [giannakakis2022review]
- **Data:** a review of EEG, ECG, EDA, EMG, respiration and other signals.
- **Method:** a review of biosignal stress features.
- **Finding:** heart rate, HRV and EDA are the most consistent stress markers, but they vary between people.
- **Relevance:** justifies the choice of heart-rate, EDA and HRV features.

**Can et al., 2019** — *J. Biomed. Inform.* [can2019survey]
- **Data:** a survey of studies using smartphones and wearables.
- **Method:** a survey of daily-life stress detection.
- **Finding:** there is a gap between laboratory results and field results, and personal differences matter.
- **Relevance:** gives context for why lab results may not transfer to daily life.

**Kim et al., 2018** — *Psychiatry Investig.* [kim2018hrv]
- **Data:** a meta-analysis of 37 studies.
- **Method:** a review of how HRV responds to stress.
- **Finding:** stress mostly lowers parasympathetic indices.
- **Relevance:** justifies RMSSD and SDNN as features.

### Benchmark datasets

**Schmidt et al., 2018 (WESAD)** — ICMI [schmidt2018wesad]
- **Data:** WESAD, 15 participants, chest and wrist sensors (ECG, EDA, BVP and others).
- **Method:** a new public dataset with feature-based benchmarks.
- **Evaluation:** leave-one-subject-out (LOSO), as described by the original paper and by secondary reports.
- **Finding:** up to 93 % accuracy for stress vs. non-stress.
- **Limitation for this project:** research-grade sensors and only 15 participants.

**Hosseini et al., 2022** — *Sci. Data* [hosseini2022nurses]
- **Data:** nurses in a hospital, Empatica E4.
- **Method:** a field stress dataset.
- **Finding:** provides real-world labels.
- **Relevance:** an example of field data, in contrast with lab data.

**Calvo et al., 2026 (QoL_Stress)** — PhysioNet [calvo2026qolstress]
- **Data:** 66 adults with a Fitbit Charge 6 recording HR, ECG at 250 Hz and EDA, plus PSS-14 and STAI-S questionnaires.
- **Method:** a dataset release. The authors' own modelling manuscript is "under preparation".
- **Finding:** no published modelling results were found.
- **Relevance:** this is the dataset used here.

### Laboratory and field stress-detection studies

**Healey & Picard, 2005** — *IEEE T-ITS* [healey2005driving]
- **Data:** real-world driving, with ECG, EMG, skin conductance and respiration.
- **Method:** stress detection.
- **Finding:** skin conductance and heart rate correlate most strongly with driver stress.
- **Relevance:** foundational for heart-rate-based stress work.

**Hovsepian et al., 2015 (cStress)** — UbiComp [hovsepian2015cstress]
- **Data:** chest ECG and respiration; 21 participants in the lab for training, then 26 in the lab and 20 in the field for testing.
- **Method:** a cross-study model. It used participant-specific normalization of features.
- **Evaluation:** validation on separate cohorts.
- **Finding:** 72 % accuracy in the field against self-reports.
- **Relevance:** uses per-person normalization, but that is not ablated against absolute features on the same test participants.

**Gjoreski et al., 2017** — *J. Biomed. Inform.* [gjoreski2017context]
- **Data:** a wrist device with BVP, EDA and accelerometer, in lab and field.
- **Method:** a lab detector combined with context and activity information.
- **Evaluation:** LOSO in the lab; real-life evaluation in the field.
- **Finding:** in the field, it detected 70 % of stress events with 95 % precision when context was used.
- **Relevance:** shows the importance of activity and context.

**Siirtola, 2019** — UbiComp/ISWC Adj. [siirtola2019smartwatch]
- **Data:** commercial smartwatch sensors, without EDA.
- **Method:** user-independent stress detection.
- **Finding:** EDA is not needed if the analysis windows are long enough.
- **Relevance:** supports models without EDA on consumer devices.

**Mishra et al., 2020** — *IMWUT* [mishra2020reproducibility]
- **Data:** four lab studies with 90 participants and two sensor types.
- **Method:** a reproducibility study testing models across studies.
- **Finding:** performance drops across studies; a clustering method for setting thresholds helps.
- **Relevance:** generalization fails across protocols.

**Smets et al., 2018** — *npj Digit. Med.* [smets2018digital]
- **Data:** 1,002 people over 5 days of daily life.
- **Method:** association analysis.
- **Finding:** "digital phenotypes" emerged; personalized models are needed.
- **Relevance:** supports the motivation for personalization.

**Pakhomov et al., 2020** — *PLOS ONE* [pakhomov2020fitbit]
- **Data:** 18 students wearing a Fitbit in daily life.
- **Method:** a within-subject comparison of HR during stress.
- **Finding:** HR rose by about 3–9 bpm during stressful periods.
- **Relevance:** Fitbit HR does respond to stress, but this was not a classifier evaluated on unseen participants.

**Bent et al., 2020** — *npj Digit. Med.* [bent2020optical]
- **Data:** consumer and research wearables, optical HR.
- **Method:** an accuracy study.
- **Finding:** error is about 30 % larger during activity.
- **Relevance:** device and activity confounds matter.

### Personalization

**Taylor et al., 2020** — *IEEE TAC* [taylor2020multitask]
- **Data:** SNAPSHOT, with surveys, wearables and phone data.
- **Method:** personalized multitask models of mood, stress and health.
- **Finding:** personalization helps.
- **Relevance:** forecasting from daily-life data, not acute stress.

**Tervonen et al., 2020** — *Comput. Biol. Med.* [tervonen2020som]
- **Data:** lab and field physiology.
- **Method:** a personalized self-organizing map (SOM).
- **Finding:** the fully personal model reached 92 % in the lab; about 60 % in the field regardless of personalization.
- **Relevance:** personalization gains did not carry over to the field.

**Nkurikiyeyezu et al., 2020** — *Sensors & Materials* [nkurikiyeyezu2020person]
- **Data:** SWELL/WESAD-type HRV data.
- **Method:** calibrating a generic model with person-specific samples.
- **Evaluation:** calibration samples are taken from the test person, so this is not participant-independent.
- **Finding:** accuracy rose from 42.5 % to 95.2 % with 100 calibration samples.
- **Limitation:** the calibration uses *labelled* data from the test person.

**Sah & Ghasemzadeh, 2021** — arXiv preprint, not peer-reviewed [sah2021personalization]
- **Data:** WESAD.
- **Method:** LOSO followed by retraining with the held-out person's data.
- **Finding:** personalization improves results.
- **Limitation:** retraining uses labels from the test person.

### Methodology

**Saeb et al., 2017** — *GigaScience* [saeb2017usecase]
- **Data:** a simulation and an activity dataset.
- **Method:** compares record-wise and subject-wise cross-validation.
- **Finding:** record-wise CV greatly overestimates accuracy.
- **Relevance:** directly motivates the leakage experiment here.

**Varoquaux, 2018** — *NeuroImage* [varoquaux2018cv]
- **Method:** an analysis of cross-validation error bars.
- **Finding:** error bars of about ±10 % are typical at n ≈ 100.
- **Relevance:** motivates reporting bootstrap CIs and avoiding strong claims.

---

## 2. Research-gap matrix

For each study: the problem it addressed, its dataset and protocol, its main limitation, what remains unresolved, and how this project differs.

**WESAD benchmark** [schmidt2018wesad]
- **Problem:** stress vs. non-stress classification.
- **Dataset and protocol:** WESAD (15 participants), LOSO.
- **Limitation:** research-grade chest and wrist sensors; a small n.
- **Unresolved:** whether results hold for a consumer, HR-only wrist signal.
- **This project:** uses a consumer Fitbit HR stream and 57 participants.

**cStress** [hovsepian2015cstress]
- **Problem:** continuous stress estimation.
- **Dataset and protocol:** separate lab and field cohorts.
- **Limitation:** per-person normalization is part of the pipeline, but it is not ablated against absolute features.
- **Unresolved:** how much normalization adds on its own.
- **This project:** ablates absolute (A), relative-only (R) and combined (A+R) features on the same folds.

**Nkurikiyeyezu 2020; Sah 2021** [nkurikiyeyezu2020person, sah2021personalization]
- **Problem:** personalizing generic models.
- **Dataset and protocol:** HRV data, WESAD; LOSO plus calibration.
- **Limitation:** calibration uses *labelled* stress data from the test person.
- **Unresolved:** whether *label-free* resting calibration helps unseen participants.
- **This project:** uses label-free calibration only (the first 3 minutes of rest), which is excluded from scoring.

**Tervonen 2020** [tervonen2020som]
- **Problem:** a personalized unsupervised model.
- **Dataset and protocol:** lab and field.
- **Limitation:** personalization is defined within each person.
- **Unresolved:** the effect on unseen participants.
- **This project:** evaluates participant-independent CV with paired tests.

**Siirtola 2019** [siirtola2019smartwatch]
- **Problem:** smartwatch stress detection without EDA.
- **Dataset and protocol:** commercial watch data, user-independent evaluation.
- **Limitation:** no personalization ablation and no confound controls.
- **Unresolved:** whether the gains come from stress or from timing.
- **This project:** adds time-only, temporally matched and drift controls.

**Saeb 2017; Varoquaux 2018** [saeb2017usecase, varoquaux2018cv]
- **Problem:** CV leakage and uncertainty.
- **Dataset and protocol:** general (not stress-specific).
- **Limitation:** not stress-specific.
- **Unresolved:** the size of the effect on a consumer-wearable stress dataset.
- **This project:** quantifies the gap between record-wise and participant-wise CV on QoL_Stress.

**Mishra 2020** [mishra2020reproducibility]
- **Problem:** cross-study reproducibility.
- **Dataset and protocol:** 4 lab studies.
- **Limitation:** uses research sensors.
- **Unresolved:** how reproducible results are on consumer devices.
- **This project:** single dataset only; cross-study generalization is left as a limitation.

**Pakhomov 2020** [pakhomov2020fitbit]
- **Problem:** Fitbit HR response to stress.
- **Dataset and protocol:** 18 students; within-subject, not a classifier.
- **Limitation:** no evaluation on unseen participants.
- **Unresolved:** classification performance on unseen people.
- **This project:** participant-independent classification.

**QoL_Stress release** [calvo2026qolstress]
- **Problem:** releasing the dataset.
- **Limitation:** no modelling paper yet.
- **Unresolved:** baseline results and a usable protocol for the timing of HR data.
- **This project:** reconstructs the phases, documents the assumptions and reports baselines.

---

## 3. Selected research direction and question

The provisional title, about evaluating individualized physiological features, was **narrowed**. Inspecting the dataset showed four things:

1. The only valid moment-level label is the protocol phase (relax vs. induced stress). PSS-14 refers to the past month, and STAI-S is given only twice per person.
2. A label-free personal baseline can legitimately be taken from the first minutes of each recording.
3. The protocol always places stress after relax. That makes time-on-task a strong confound, which any claim must control for.
4. The ECG and EDA recordings are taken at the *end* of each phase, after the stressor. Phase-level ECG and EDA therefore may not reflect the stressor itself.

**Final title:** *Do Baseline-Relative Heart-Rate Features Help Recognize Induced Stress in Unseen Participants? A Confound-Aware Evaluation on the QoL_Stress Consumer-Wearable Dataset.*

**Research questions:**

- **RQ1.** Under participant-independent cross-validation, do features relative to a label-free resting calibration (R, A+R) classify relax vs. induced-stress windows better than absolute Fitbit heart-rate features (A)? The comparison uses the same participants and the same folds.
- **RQ2.** Do phase-level EDA and ECG-derived ultra-short HRV add information beyond heart rate?
- **RQ3.** How much do record-wise splitting and the fixed protocol order (time-on-task) affect the reported performance?

## 4. Evidence supporting the contribution

- **The ablation is paired and label-free.** The personalization studies found (Section 1) either calibrate with *labelled* data from the test person [nkurikiyeyezu2020person, sah2021personalization], or evaluate within each person [tervonen2020som]. Others build normalization into a pipeline without ablating it [hovsepian2015cstress]. In the reviewed literature, limited comparative evidence was found for **label-free** baseline features tested on **unseen participants** with **paired, identical folds** on consumer HR.
- **The confound controls are new for this dataset.** No reviewed study on QoL_Stress exists. Among the reviewed lab studies, explicit time-on-task controls (time-only classifier, temporally matched windows, within-phase drift classifier) were not reported. This is stated as "not found in the reviewed sources", not as absent from the whole field.
- **Leakage is quantified on consumer data.** Saeb et al. show record-wise inflation in general [saeb2017usecase]. This study measures it on this dataset and these features.
- **The dataset is new.** QoL_Stress was released in October 2026, and its authors' own modelling paper is unpublished. No peer-reviewed model results on it were found.
- **The contribution stands even if B does not beat A.** It rests on rigorous evaluation and controls, not on a particular result.

## 5. Remaining novelty uncertainties

- The search was targeted, not systematic. Similar ablations may exist in venues that were not searched, for example IEEE EMBC/BSN proceedings and MDPI *Sensors*. Before submission, search IEEE Xplore and ACM DL directly for "baseline normalization" with "leave-one-subject-out" and "stress".
- The QoL_Stress authors' manuscript may appear before or during review, and it may report overlapping baselines.
- Per-participant normalization in general is **not** novel [hovsepian2015cstress]. The contribution is limited to the evaluation design and the findings on this dataset.

## 6. Verification log for the references

How each reference was checked:

- **Dataset page** (title, DOI, license, protocol, ECG at 250 Hz, Fitbit Charge 6, manuscript in preparation): calvo2026qolstress.
- **Dataset page and PhysioNet "about" page:** pollard2026physionet. The DOI page itself was not opened.
- **Search results and OpenAlex/third-party records** (DOI, pages 400–408): schmidt2018wesad.
- **arXiv journal-reference line:** vos2023generalizable.
- **arXiv author list:** hosseini2022nurses.
- **PubMed author list:** tervonen2020som.
- **Publisher, PMC, PubMed, dblp or DOI records seen in search results:** schmidt2019review, giannakakis2022review, can2019survey, kim2018hrv, healey2005driving, gjoreski2017context, hovsepian2015cstress, mishra2020reproducibility, siirtola2019smartwatch, smets2018digital, taylor2020multitask, saeb2017usecase, varoquaux2018cv, bent2020optical, pakhomov2020fitbit (PLOS page fetched), cohen1983pss, stroop1935, pan1985qrs, taskforce1996hrv.
- **Search results (journal, volume, issue, pages):** nkurikiyeyezu2020person. **The DOI could not be confirmed**, so none is given.
- **arXiv listing; preprint, labelled as not peer reviewed:** sah2021personalization.
- **Standard references** whose bibliographic details are well established but were not re-fetched this session: pedregosa2011sklearn, holm1979, wilcoxon1945, spielberger1983stai. Check them against the publisher pages before submission.
