from BERTfunctions import *
import pandas as pd

labels = pd.read_csv("./ClassifyEdges/edge_labels.csv", sep=";")

model = BERTedgeReclassifier()

# il paragrafo da classificare in input ha la forma:
# RIGA 1: contiene articolo da classificare con struttura: articolo <numero articolo> del legge <numero legge> del <data legge>
# RIGA 3: <testo del paragrafo>
paragraph = """"Articolo 2 del legge n. 307 del 4 - 5 - 1951

L'aumento del 20 per cento degli stipendi, paghe e retribuzioni tabellari previsto, ai fini della liquidazione dei trattamenti di quiescenza, dall'art. 3 della legge 29 aprile 1949, n. 221, viene applicato limitatamente alle prime lire 250.000 annue lorde o frazioni di esse.
Resta fermo l'aumento nella misura fissa di lire 66.000 annue ai sensi del suddetto art. 3 della legge 29 aprile 1949, n. 221, modificato dall'art. 2 della legge 4 maggio 1951, n. 307.
"""

label = model.textWithRef(paragraph, labels)
print(label)


paragraph = """"Articolo 2 del legge n. 307 del 4 - 5 - 1951

L'articolo 2 della legge 307 del 4-5-1951 è stato modificato come segue:
al punto 1 le parole "bilancio quadriennale" sono sostituite da "bilancio triennale".
"""

label = model.textWithRef(paragraph, labels)
print(label)