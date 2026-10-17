ansible-playbook -i infra/ansible/inventory.ini infra/ansible/playbooks/00_cleanup_all.yml
ansible-playbook -i infra/ansible/inventory.ini infra/ansible/playbooks/01_setup_host_tools.yml 
ansible-playbook -i infra/ansible/inventory.ini infra/ansible/playbooks/02_provision_k3d_clusters.yml
ansible-playbook -i infra/ansible/inventory.ini infra/ansible/playbooks/03_reset_wan_emulation.yml
ansible-playbook -i infra/ansible/inventory.ini infra/ansible/playbooks/04_emulate_wan_latency.yml
ansible-playbook -i infra/ansible/inventory.ini infra/ansible/playbooks/05_deploy_hub_storage.yml
ansible-playbook -i infra/ansible/inventory.ini infra/ansible/playbooks/06_deploy_hub_observability.yml
ansible-playbook -i infra/ansible/inventory.ini infra/ansible/playbooks/