# Evolutionary relationships among coronaviruses: where does SARS-CoV-2 fit?

**Student registration number:** 2021/ICT/115

## 1. Abstract

Coronaviruses have caused three major human outbreaks since 2002, and tracing the origin of SARS-CoV-2 depends on knowing its relatives. I analysed 15 complete coronavirus genomes from NCBI in R, building neighbour-joining and maximum-likelihood trees from the codon-aligned nucleocapsid (N) gene (GTR+G+I model, 50 bootstraps) and a spike-gene tree for betacoronaviruses. SARS-CoV-2 grouped with the bat virus RaTG13 in every tree (p-distance 0.031), within a sarbecovirus clade, and apart from MERS-CoV and the common-cold coronaviruses. The N-gene NJ and ML trees differed only within the alphacoronaviruses (Robinson–Foulds distance 2), whereas the spike tree arranged SARS-CoV and the merbecoviruses differently. The results support a bat-virus origin of the lineage, but one gene and 15 viruses cannot show how it reached humans.

## 2. Introduction

Coronaviruses (subfamily *Orthocoronavirinae*) are enveloped RNA viruses with genomes of roughly 27–32 kb that infect birds and mammals. They are classified into four genera: *Alpha-*, *Beta-*, *Gamma-* and *Deltacoronavirus*. Seven coronaviruses are known to infect humans. HCoV-229E and HCoV-NL63 (alphacoronaviruses) and HCoV-OC43 and HCoV-HKU1 (betacoronaviruses) usually cause mild respiratory illness, whereas SARS-CoV (2002), MERS-CoV (2012) and SARS-CoV-2 (2019) caused severe disease and large outbreaks. SARS-CoV, MERS-CoV and SARS-CoV-2 are thought to have bat-borne ancestors, reaching people directly or through intermediate animal hosts (Zhou *et al.*, 2020; Andersen *et al.*, 2020).

When a new virus emerges, one of the first questions is which known viruses it is most closely related to. Phylogenetic analysis answers this by placing the virus on the coronavirus family tree. The answer helps to identify likely animal reservoirs, directs surveillance towards related animal viruses with spillover potential, and shows how much knowledge about close relatives is likely to transfer. For SARS-CoV-2, the bat virus RaTG13 shares about 96% of its genome sequence (Zhou *et al.*, 2020), but the wider relationships are best understood by comparing several viruses within one consistent analysis.

**Aim.** To reconstruct the evolutionary relationships among 15 representative coronaviruses from three genera and to determine which of them are the closest relatives of SARS-CoV-2.

**Hypotheses.**

1. SARS-CoV-2 clusters with the bat virus RaTG13 and the other sarbecoviruses (SARS-CoV and bat SARS-like viruses), and not with MERS-CoV or the common-cold coronaviruses.
2. Trees built from the conserved nucleocapsid gene and from the more variable spike gene agree on the major groupings, although differences may appear because coronaviruses recombine.

## 3. Data

**Source.** Complete genome sequences from NCBI Nucleotide (RefSeq and GenBank), downloaded in R with the `rentrez` package on 14 November 2026. Accessions, taxonomy and host are in [`data/virus_metadata.csv`](data/virus_metadata.csv). The sequences are cached in `data/fasta/` and the GenBank annotation files in `data/genbank/`.

**Description and size.** 15 viruses from three genera, chosen to cover the main lineages around SARS-CoV-2 and to include an outgroup. Each genome is 27–31 kb, 442,465 nucleotides in total.

**Table 1. Coronaviruses used in this study.**

| Virus | Accession | Genus | Host | Genome length (nt) | GC (%) |
|---|---|---|---|---|---|
| SARS-CoV-2 | NC_045512.2 | Beta | Human | 29,903 | 38.0 |
| RaTG13 | MN996532.2 | Beta | Bat | 29,855 | 38.0 |
| SL-ZC45 | MG772933.1 | Beta | Bat | 29,802 | 38.9 |
| SL-ZXC21 | MG772934.1 | Beta | Bat | 29,732 | 38.8 |
| SARS-CoV | NC_004718.3 | Beta | Human | 29,751 | 40.8 |
| MERS-CoV | NC_019843.3 | Beta | Human | 30,119 | 41.2 |
| BatCoV-HKU4 | NC_009019.1 | Beta | Bat | 30,286 | 37.8 |
| BatCoV-HKU5 | NC_009020.1 | Beta | Bat | 30,482 | 43.2 |
| HCoV-OC43 | NC_006213.1 | Beta | Human | 30,741 | 36.8 |
| HCoV-HKU1 | NC_006577.2 | Beta | Human | 29,926 | 32.1 |
| MHV | NC_001846.1 | Beta | Mouse | 31,357 | 41.8 |
| HCoV-229E | NC_002645.1 | Alpha | Human | 27,317 | 38.3 |
| HCoV-NL63 | NC_005831.2 | Alpha | Human | 27,553 | 34.5 |
| PEDV | NC_003436.1 | Alpha | Pig | 28,033 | 42.0 |
| IBV | NC_001451.1 | Gamma | Chicken | 27,608 | 37.9 |

**Variables.** Accession, short name, genus, lineage and host (from the metadata table), plus genome length, GC content and the number of ambiguous bases calculated in R. No genome contained ambiguous bases (N).

**Licensing and ethics.** The sequences are public records from NCBI, which places no restrictions on their use. Only viral sequences are used: no human participants, personal data or live virus work are involved, so no ethical approval was needed.

## 4. Methods

All analyses were done in R 4.6.2 using RStudio. The code is in `code/01_data_qc_alignment.R` (data, QC, alignment, distances), `code/02_trees_spike.R` (trees and spike analysis) and `code/helpers.R` (plotting and bootstrap-support functions). The R Markdown report `code/coronavirus_report.Rmd` reads the saved results and produces an HTML version of this report.

1. **Retrieval and quality control.** Genomes were downloaded with `rentrez` (Winter, 2017) and cached so the analysis can be repeated offline. Genome length, GC content and ambiguous bases were calculated with `Biostrings` and visualised with `ggplot2` (Wickham, 2016). This checks that the sequences are complete and comparable before any analysis.
2. **Choice of marker.** Aligning whole 30 kb genomes from three genera is slow and unreliable, because the genomes are highly divergent in places and differ in gene content, and my preliminary attempts at whole-genome alignment did not finish in a practical time. I therefore used the nucleocapsid (N) gene, which is present in every coronavirus and is a single continuous reading frame. It was extracted from each GenBank annotation by selecting the longest coding sequence whose product name contained "nucleocapsid" or "nucleoprotein". All 15 viruses were recovered (1,134–1,365 nt).
3. **Alignment and trimming.** N-gene sequences were aligned codon-aware with `DECIPHER::AlignTranslation` (Wright, 2016), which aligns the translated protein and maps the result back to DNA. This is more reliable than aligning raw DNA when sequences are distantly related. Columns with gaps in more than 50% of sequences were removed, reducing the alignment from 1,761 to 1,245 columns.
4. **Distances.** Pairwise p-distances (proportion of differing sites) were calculated with `phangorn` (Schliep, 2011) and shown as a clustered heatmap with `pheatmap`.
5. **Distance-based trees.** Neighbour-joining (NJ) trees (Saitou and Nei, 1987) were built from Jukes–Cantor distances. A UPGMA tree was drawn for comparison only, because it assumes a constant evolutionary rate, which is unrealistic here.
6. **Maximum-likelihood (ML) tree.** `modelTest` compared substitution models (JC, HKY and GTR, each with and without gamma-distributed rate variation and invariant sites) using AIC and BIC. The ML tree was optimised with `optim.pml`, starting from the NJ tree and using nearest-neighbour-interchange rearrangements. ML is generally preferred to NJ because it uses an explicit model of sequence evolution.
7. **Rooting and support.** Trees were rooted on the gammacoronavirus IBV, the most distant lineage in the data set, using `ape` (Paradis and Schliep, 2019). Branch support is the percentage of 50 bootstrap trees (Felsenstein, 1985) that contain the same split, calculated with a function in `helpers.R` and printed on nodes with at least 50% support. Nodes with at least 70% support were treated as well supported. Fifty replicates is fewer than the usual 100 or more, so support values are approximate.
8. **Tree comparison.** The unrooted NJ and ML topologies were compared with the Robinson–Foulds distance (`phangorn::RF.dist`), where 0 means identical topologies.
9. **Spike gene.** The spike coding sequence was extracted in the same way. It was found for 14 of 15 viruses (not for MHV). The ten betacoronaviruses with spike sequences were aligned with `msa` (Clustal Omega; Bodenhofer *et al.*, 2015), trimmed in the same way, and used to build an NJ tree with 50 bootstraps, rooted on HCoV-OC43. Only betacoronaviruses were used because spike sequences from different genera are too divergent to align well.

## 5. Results

### 5.1 Genome features

![Figure 1. Genome length and GC content of the 15 coronaviruses, coloured by genus; point shape shows the host.](figures/fig1_genome_qc.png)

Genome length differed clearly between groups (Table 1, Figure 1). The alphacoronaviruses and the gammacoronavirus IBV had the shortest genomes (27,317–28,033 nt), whereas the betacoronaviruses ranged from 29,732 to 31,357 nt, with MHV the longest. GC content ranged from 32.1% in HCoV-HKU1 to 43.2% in BatCoV-HKU5. SARS-CoV-2 and RaTG13 were almost identical in both features. Genome length and GC content are descriptive only and were not used for tree building. The trimmed N-gene alignment had 1,245 sites.

### 5.2 Genetic distances

![Figure 2. Pairwise p-distance of the nucleocapsid gene, with hierarchical clustering and genus annotation.](figures/fig2_distance_heatmap.png)

The heatmap (Figure 2) shows four blocks of closely related viruses along the diagonal: the sarbecoviruses, the merbecoviruses (MERS-CoV, HKU4, HKU5), the embecoviruses (HKU1, OC43, MHV) and the alphacoronaviruses. Distances between lineages were much larger, about 0.4 or more, and the largest was between SARS-CoV and PEDV (0.54). The gammacoronavirus IBV was about equally distant from every other virus, as expected for an outgroup. Hierarchical clustering on the heatmap separated the same lineages.

SARS-CoV-2 was closest to RaTG13 (p-distance 0.031), followed by the two bat SARS-like viruses and SARS-CoV, which was about four times as distant as RaTG13. MERS-CoV was much more distant (Table 2).

**Table 2. N-gene p-distance between SARS-CoV-2 and selected viruses.**

| Virus | p-distance to SARS-CoV-2 |
|---|---|
| RaTG13 | 0.0305 |
| SL-ZXC21 | 0.0884 |
| SL-ZC45 | 0.0892 |
| SARS-CoV | 0.1173 |
| MERS-CoV | 0.4337 |

### 5.3 Neighbour-joining tree

![Figure 3. Neighbour-joining tree of the N gene (Jukes–Cantor distances), rooted on IBV. Numbers at nodes are bootstrap support (%), shown when at least 50%. Tip colours show the genus.](figures/fig3_nj_tree.png)

The NJ tree (Figure 3) recovered the three genera, with the betacoronaviruses and the alphacoronaviruses each forming a single group. Within the betacoronaviruses there were three lineages: the sarbecoviruses, the merbecoviruses and the embecoviruses, with the sarbecoviruses and merbecoviruses as sister groups and the embecoviruses outside them. SARS-CoV-2 and RaTG13 formed a pair. Their closest relatives were SARS-CoV and the two bat SARS-like viruses SL-ZC45 and SL-ZXC21, which formed a second group in which the two bat viruses were sisters. Among the merbecoviruses, MERS-CoV was placed outside the two bat viruses HKU4 and HKU5. Among the alphacoronaviruses, HCoV-NL63 was placed outside PEDV and HCoV-229E.

![Figure 4. UPGMA tree of the N gene, shown for comparison only (it assumes a constant evolutionary rate and has no outgroup).](figures/fig6_upgma_tree.png)

The UPGMA tree (Figure 4) found the same lineages but differed from the NJ and ML trees in two ways. It placed SARS-CoV outside a group formed by SARS-CoV-2, RaTG13 and the two bat SARS-like viruses, and it split the alphacoronaviruses from all other viruses with IBV next to the betacoronaviruses. This is an artefact of the constant-rate assumption: the viruses have evolved at different speeds, and the long-branch alphacoronaviruses are pulled to the base of the tree. UPGMA was therefore not used for the main conclusions.

### 5.4 Maximum-likelihood tree

**Table 3. The six best substitution models for the N-gene alignment, ranked by BIC.**

| Model | Parameters | Log-likelihood | AIC | BIC |
|---|---|---|---|---|
| GTR+G(4)+I | 37 | −14379.2 | 28832.5 | 29022.2 |
| GTR+G(4) | 36 | −14383.3 | 28838.6 | 29023.2 |
| HKY+G(4)+I | 33 | −14408.7 | 28883.4 | 29052.6 |
| HKY+G(4) | 32 | −14415.8 | 28895.5 | 29059.6 |
| GTR+I | 36 | −14469.0 | 29010.1 | 29194.6 |
| HKY+I | 32 | −14493.6 | 29051.2 | 29215.3 |

The best model was GTR+G(4)+I by both AIC and BIC (AIC weight 0.96; final log-likelihood −14378.95 after tree optimisation). Models that allowed rate variation among sites fitted far better than models that did not, which is expected for a protein-coding gene where third codon positions change much faster than the others.

![Figure 5. Maximum-likelihood tree of the N gene (GTR+G+I), rooted on IBV, with bootstrap support (%) at nodes with at least 50%.](figures/fig4_ml_tree.png)

The ML tree (Figure 5) had the same lineages as the NJ tree, and SARS-CoV-2 and RaTG13 again formed a pair within the sarbecoviruses, with SARS-CoV grouped with the two bat SARS-like viruses. The NJ and ML trees differed by a Robinson–Foulds distance of 2, which corresponds to one rearranged branch. It lies within the alphacoronaviruses, where ML places HCoV-229E outside PEDV and HCoV-NL63, the reverse of the NJ arrangement. All other relationships were the same in both methods.

### 5.5 Spike gene

![Figure 6. Neighbour-joining tree of the spike gene for the betacoronaviruses, rooted on HCoV-OC43, with bootstrap support (%) at nodes with at least 50%.](figures/fig5_spike_tree.png)

The spike sequence was recovered for 14 of 15 viruses (not for MHV), so the spike tree (Figure 6) contains ten betacoronaviruses. It agreed with the N-gene trees on the main features: SARS-CoV-2 and RaTG13 were sisters, the sarbecoviruses formed one group and the merbecoviruses another. It differed in two places. First, SARS-CoV was placed outside a group made of SARS-CoV-2, RaTG13 and the two bat SARS-like viruses, whereas in the N-gene trees SARS-CoV grouped with the two bat viruses. Second, HKU4 was placed outside MERS-CoV and HKU5, whereas MERS-CoV was the outer virus in the N-gene trees.

## 6. Discussion

**Relationship of SARS-CoV-2 to other coronaviruses.** In all trees SARS-CoV-2 grouped with the bat virus RaTG13, inside a sarbecovirus group that also contained SARS-CoV and two bat SARS-like viruses, and well away from MERS-CoV and the common-cold coronaviruses. The N-gene distances show the same ranking: SARS-CoV-2 differed from RaTG13 at 0.031 of sites, from SARS-CoV at about four times that, and from MERS-CoV at 0.43. Hypothesis 1 is therefore supported, and the result agrees with the proposed bat origin of the lineage (Zhou *et al.*, 2020; Andersen *et al.*, 2020). The bootstrap values on the nodes of Figures 3, 5 and 6 show how strongly each grouping is supported.

**Agreement between genes and methods.** Hypothesis 2 is partly supported. The N-gene and spike trees agree on the major lineages (sarbecoviruses, merbecoviruses, embecoviruses) and on the SARS-CoV-2–RaTG13 pair, but disagree on the position of SARS-CoV and the order of the merbecoviruses. One possible explanation is recombination, which is common among sarbecoviruses (Boni *et al.*, 2020) and can give different genes different histories. Another is that spike is under different selection from N because it binds host receptors. These explanations are untested here, and the differences may also reflect limited signal: each tree rests on one gene of about 1.2 kb (N) or 3.5–4 kb (spike), with only 50 bootstraps. The NJ and ML trees were nearly identical (Robinson–Foulds distance 2), so the N-gene result does not depend much on the method, whereas the UPGMA tree showed why a constant-rate method is unsuitable for these data.

**Real-world implications.** Placing a newly found coronavirus on a tree of known viruses, as done here with a single conserved gene, is a fast first step in an outbreak. It shows which known viruses to compare with, which animal groups to sample, and whether findings about relatives (for example on drug targets) may carry over. The close link between SARS-CoV-2 and bat sarbecoviruses supports continued surveillance of coronaviruses in bats and other wildlife.

**Limitations.**

- Only 15 viruses were sampled. Closer relatives of SARS-CoV-2 than RaTG13 have since been described (Temmam *et al.*, 2022), and no intermediate hosts are included, so the trees say nothing about how the virus reached humans.
- One gene gives one view of the evolutionary history, and recombination can hide in a single tree. A whole-genome or multi-gene analysis would be stronger.
- Between different lineages the N-gene p-distances were close to 0.5, which suggests that many sites have changed more than once. Deep relationships between genera are therefore poorly resolved, and only the groupings within lineages should be considered reliable.
- Fifty bootstrap replicates are fewer than usual, so support values are approximate.
- The spike gene could not be extracted for MHV, and spike sequences from different genera were not aligned.
- NJ trees used the simple Jukes–Cantor model, and the ML analysis was started from one tree.

## 7. Conclusion and future work

This project placed SARS-CoV-2 on a tree of 15 coronaviruses using R. In every tree SARS-CoV-2 was sister to the bat virus RaTG13, within a sarbecovirus group, and far from MERS-CoV and the common-cold coronaviruses. Neighbour-joining and maximum-likelihood trees of the N gene differed only in the order of three alphacoronaviruses, while the spike tree placed SARS-CoV and the merbecoviruses differently, which shows that different genes can tell slightly different stories. These results fit a bat-virus origin of the SARS-CoV-2 lineage, but they cannot show the route to humans. Future work should add more sarbecoviruses (including newer bat viruses and viruses from pangolins and civets), analyse several genes or whole genomes, test for recombination, use more bootstrap replicates, and apply dated Bayesian methods to estimate when the lineages split.

## 8. Reproducibility

**Repository structure**

```
.
├── README.md                      this report
├── code/
│   ├── helpers.R                  plotting and bootstrap-support functions
│   ├── 01_data_qc_alignment.R     data, QC, alignment, distances
│   ├── 02_trees_spike.R           trees, model selection, spike analysis
│   └── coronavirus_report.Rmd     R Markdown report (HTML version of this README)
├── data/                          metadata table, downloaded FASTA and GenBank files
├── figures/                       all figures used in this report
└── results/                       tables, alignments, trees, saved objects, rendered HTML
```

**Required software.** R 4.6.2. Packages: tidyverse 2.0.0 (including ggplot2 4.0.3), rentrez 1.2.4, ape 5.8-1, phangorn 2.12.1, pheatmap 1.0.13, ggrepel and rmarkdown (CRAN); Biostrings 2.80.2, msa 1.44.1 and DECIPHER 3.8.1 (Bioconductor 3.23). The full `sessionInfo()` is saved in `results/sessionInfo.txt` and at the end of the HTML report.

**How to run**

```r
# 1. Install packages (once)
install.packages(c("tidyverse", "rentrez", "ape", "phangorn", "pheatmap", "ggrepel", "rmarkdown", "BiocManager"))
BiocManager::install(c("Biostrings", "msa", "DECIPHER"))

# 2. Set the working directory to the repository folder, then run the scripts in order
setwd("path/to/this/repository")
source("code/01_data_qc_alignment.R")   # downloads data (needs internet the first time), a few minutes
source("code/02_trees_spike.R")         # model test and bootstraps, can take 10-30 minutes

# 3. Render the HTML report
rmarkdown::render("code/coronavirus_report.Rmd", output_dir = "results")
```

The downloaded sequences are cached in `data/`, so later runs work offline. The random seed is 123 and the number of bootstrap replicates is set by `n_boot` at the top of `02_trees_spike.R`. The rendered report is `results/coronavirus_report.html`.

## 9. References

Andersen, K.G., Rambaut, A., Lipkin, W.I., Holmes, E.C. and Garry, R.F. (2020) 'The proximal origin of SARS-CoV-2', *Nature Medicine*, 26, pp. 450–452.

Bodenhofer, U., Bonatesta, E., Horejš-Kainrath, C. and Hochreiter, S. (2015) 'msa: an R package for multiple sequence alignment', *Bioinformatics*, 31(24), pp. 3997–3999.

Boni, M.F. *et al.* (2020) 'Evolutionary origins of the SARS-CoV-2 sarbecovirus lineage responsible for the COVID-19 pandemic', *Nature Microbiology*, 5, pp. 1408–1417.

Felsenstein, J. (1985) 'Confidence limits on phylogenies: an approach using the bootstrap', *Evolution*, 39(4), pp. 783–791.

Kolde, R. *pheatmap: Pretty Heatmaps*. R package.

Pagès, H., Aboyoun, P., Gentleman, R. and DebRoy, S. *Biostrings: Efficient manipulation of biological strings*. R package.

Paradis, E. and Schliep, K. (2019) 'ape 5.0: an environment for modern phylogenetics and evolutionary analyses in R', *Bioinformatics*, 35(3), pp. 526–528.

R Core Team (2026) *R: A language and environment for statistical computing*. Vienna: R Foundation for Statistical Computing.

Saitou, N. and Nei, M. (1987) 'The neighbor-joining method: a new method for reconstructing phylogenetic trees', *Molecular Biology and Evolution*, 4(4), pp. 406–425.

Schliep, K.P. (2011) 'phangorn: phylogenetic analysis in R', *Bioinformatics*, 27(4), pp. 592–593.

Slowikowski, K. *ggrepel: Automatically position non-overlapping text labels with ggplot2*. R package.

Temmam, S. *et al.* (2022) 'Bat coronaviruses related to SARS-CoV-2 and infectious for human cells', *Nature*, 604, pp. 330–336.

Wickham, H. (2016) *ggplot2: Elegant graphics for data analysis*. New York: Springer.

Wickham, H. *et al.* (2019) 'Welcome to the tidyverse', *Journal of Open Source Software*, 4(43), 1686.

Winter, D.J. (2017) 'rentrez: an R package for the NCBI eUtils API', *The R Journal*, 9(2), pp. 520–526.

Wright, E.S. (2016) 'Using DECIPHER v2.0 to analyze big biological sequence data in R', *The R Journal*, 8(1), pp. 352–359.

Zhou, P. *et al.* (2020) 'A pneumonia outbreak associated with a new coronavirus of probable bat origin', *Nature*, 579, pp. 270–273.

**Datasets.** NCBI Nucleotide database (https://www.ncbi.nlm.nih.gov/nuccore/), accessed 14 November 2026. The 15 genome sequences are cited by accession in Table 1.
