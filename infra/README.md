# Bước 1: Cài đặt công cụ nền tảng
ansible-playbook -i infra/ansible/inventory.ini infra/ansible/playbooks/01_setup_host.yml 

# Bước 2: Tạo mạng và 3 cụm k3d
ansible-playbook -i infra/ansible/inventory.ini infra/ansible/playbooks/02_create_clusters.yml

# Bước 3: Áp cấu hình trễ mạng WAN ảo
ansible-playbook -i infra/ansible/inventory.ini infra/ansible/playbooks/03_setup_wan_emulation.yml 