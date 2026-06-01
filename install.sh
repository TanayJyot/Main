# create environment for text-to-gloss
conda create -n text-to-gloss python=3.10.16 -y
conda activate text-to-gloss
pip install -r text-to-gloss/requirements.txt
conda deactivate

# create environment for gloss-to-skeleton
conda create -n gloss-to-skeleton python=3.9 -y
conda activate gloss-to-skeleton
pip install -r pose-master/pose-master.txt
conda deactivate