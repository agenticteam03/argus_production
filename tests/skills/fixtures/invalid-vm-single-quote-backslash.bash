# --------------------------------------------------------------
# VM.1 [VM vm-095 · bash] Checker fixture: commands are data, never executed.
# Expected: the checker rejects the mutation without a SESSION guard.
echo 'C:\'
sudo docker restart argus-lab-api
echo 'end'
