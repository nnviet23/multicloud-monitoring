ansible-playbook -i infra/ansible/inventory.ini infra/ansible/playbooks/00_cleanup_all.yml
ansible-playbook -i infra/ansible/inventory.ini infra/ansible/playbooks/01_setup_host_tools.yml 
ansible-playbook -i infra/ansible/inventory.ini infra/ansible/playbooks/02_provision_k3d_clusters.yml