# Bước 1: Cài đặt công cụ nền tảng
ansible-playbook -i infra/ansible/inventory.ini infra/ansible/playbooks/01_setup_host.yml 

# Bước 2: Tạo mạng và 3 cụm k3d
ansible-playbook -i infra/ansible/inventory.ini infra/ansible/playbooks/02_create_clusters.yml

# Bước 3: Áp cấu hình trễ mạng WAN ảo
ansible-playbook -i infra/ansible/inventory.ini infra/ansible/playbooks/03_setup_wan_emulation.yml 
ansible-playbook -i infra/ansible/inventory.ini infra/ansible/playbooks/03_reset_wan_emulation.yml

docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' k3d-hub-k3d-server-0
docker exec k3d-aws-k3d-server-0 ping -c 4 172.28.0.3


ansible-playbook -i infra/ansible/inventory.ini infra/ansible/playbooks/05_deploy_hub_storage.yml
ansible-playbook -i infra/ansible/inventory.ini infra/ansible/playbooks/06_expose_hub_services.yml