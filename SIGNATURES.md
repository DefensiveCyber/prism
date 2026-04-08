# PRISM Signature Catalog

**327 signatures** across 16 categories, derived from major Splunk Technology Add-ons (TAs) and vendor log formats.

Each signature defines required patterns (must all match), optional boosters (increase confidence), and cleaning rules (how dirty lines are stripped before routing).

---

## Summary by Category

| Category | Count | Key Vendors |
|---|---|---|
| [Network](#network-79) | 79 | Palo Alto, Fortinet, Check Point, Juniper, F5, Zeek, Zscaler, Netskope, Infoblox, Arista, Bluecoat |
| [Infrastructure](#infrastructure-39) | 39 | VMware (ESXi, vCenter, NSX, vSAN, Horizon), Kubernetes, Docker |
| [Cloud](#cloud-38) | 38 | AWS (17), Azure/Entra (10), GCP (5), Google Workspace, Zoom |
| [Security](#security-36) | 36 | Okta, CyberArk, Suricata, Wazuh, HashiCorp Vault, SailPoint, GitHub, GitLab, Delinea |
| [Cisco](#cisco-31) | 31 | ASA, FTD, IOS, NX-OS, ISE, SD-WAN (11), Duo, AMP, DNA Center, Stealthwatch, ThousandEyes |
| [Windows](#windows-24) | 24 | Security, Sysmon, PowerShell, Defender, AppLocker, Code Integrity, Firewall, BITS, Print |
| [Endpoint](#endpoint-23) | 23 | CrowdStrike (3), Carbon Black (4), SentinelOne (3), Trend Micro, Trellix, Cylance |
| [Email](#email-13) | 13 | O365, Exchange, Proofpoint (2), Mimecast (3), Barracuda, Cisco Secure Email |
| [Linux](#linux-9) | 9 | auditd, iptables, auth, secure, syslog, cron |
| [Web](#web-9) | 9 | Apache, Nginx, IIS, HAProxy, Squid, Traefik, Tomcat, Envoy |
| [Database](#database-8) | 8 | MSSQL, MySQL, PostgreSQL, Oracle, MongoDB, Redis, Elasticsearch |
| [Middleware](#middleware-6) | 6 | Kafka, RabbitMQ, ActiveMQ, ZooKeeper, IBM MQ, NATS |
| [Monitoring](#monitoring-6) | 6 | Nagios, Prometheus, Icinga2, PagerDuty, ServiceNow |
| [Storage](#storage-3) | 3 | NetApp ONTAP, Dell EMC VNX, Rubrik |
| [OT/ICS](#otics-2) | 2 | Claroty, Generic OT Syslog |
| [Generic](#generic-1) | 1 | JSON (no timestamp) |

---

## Network (79)

### Palo Alto Networks
| Sourcetype | Product |
|---|---|
| `pan:traffic` | PAN-OS NGFW Traffic |
| `pan:threat` | PAN-OS NGFW Threat |
| `pan:system` | PAN-OS NGFW System |
| `pan:config` | PAN-OS NGFW Config |
| `pan:globalprotect` | GlobalProtect VPN |
| `pan:hipmatch` | HIP Match |
| `pan:decryption` | SSL/TLS Decryption |

### Fortinet
| Sourcetype | Product |
|---|---|
| `fgt_traffic` | FortiGate Traffic |
| `fgt_event` | FortiGate Event |
| `fgt_utm` | FortiGate UTM |
| `fgt_vpn` | FortiGate VPN |
| `fgt_waf` | FortiGate WAF |

### Check Point
| Sourcetype | Product |
|---|---|
| `checkpoint:firewall` | Firewall-1 |
| `checkpoint:firewall:ecs` | Firewall (ECS format) |
| `checkpoint:firewall:legacy` | Firewall (Legacy Syslog) |
| `checkpoint:smart:event` | SmartEvent |
| `checkpoint:mgmt:audit` | Management Audit |

### Juniper
| Sourcetype | Product |
|---|---|
| `juniper:junos` | JunOS (general) |
| `juniper:junos:firewall` | JunOS Firewall Filter |
| `juniper:junos:idp` | IDP/IPS |
| `juniper:junos:npu` | MX/SRX NPU |
| `juniper:srx` | SRX Firewall |
| `juniper:netscreen` | NetScreen |
| `juniper:mist:events` | Mist AI Wireless |
| `juniper:mist:audit` | Mist Audit |
| `juniper:space:syslog` | Space / Security Director |
| `juniper:apstra` | Apstra (Intent-Based Networking) |

### F5
| Sourcetype | Product |
|---|---|
| `f5:bigip:ltm` | BIG-IP LTM |
| `f5:bigip:asm` | BIG-IP ASM (WAF) |
| `f5:bigip:gtm:dns` | BIG-IP GTM/DNS |
| `f5:bigip:apm:access` | BIG-IP APM |
| `f5:bigip:irule` | BIG-IP iRule |
| `f5:bigip:syslog` | BIG-IP System Syslog |

### Zscaler
| Sourcetype | Product |
|---|---|
| `zscaler:zia:firewall` | ZIA Firewall |
| `zscaler:zia:web` | ZIA Web Proxy |
| `zscaler:zia:dns` | ZIA DNS |
| `zscaler:zia:tunnel` | ZIA Tunnel |
| `zscaler:zia:casb` | ZIA CASB |
| `zscaler:zpa:user:activity` | ZPA User Activity |
| `zscaler:zpa:user:status` | ZPA User Status |

### Netskope
| Sourcetype | Product |
|---|---|
| `netskope:events:application` | Application Events |
| `netskope:events:network` | Network Events |
| `netskope:events:alert` | Alert Events |

### Infoblox
| Sourcetype | Product |
|---|---|
| `infoblox:dns` | NIOS DNS |
| `infoblox:dhcp` | NIOS DHCP |
| `infoblox:dhcp:lease` | DHCP Lease Events |
| `infoblox:audit` | NIOS Audit Log |
| `infoblox:threat:intel` | Threat Intelligence |
| `infoblox:bloxone:threat:defense` | BloxOne Threat Defense |

### Arista
| Sourcetype | Product |
|---|---|
| `arista:eos:syslog` | EOS Switch/Router |
| `arista:eos:audit` | EOS Command Audit |
| `arista:cloudvision:syslog` | CloudVision Portal (CVP) |

### Zeek (Bro)
| Sourcetype | Product |
|---|---|
| `zeek:conn` | Connection Log |
| `zeek:dns` | DNS Log |
| `zeek:http` | HTTP Log |
| `zeek:ssl` | SSL/TLS Log |
| `zeek:files` | Files Log |
| `zeek:dhcp` | DHCP Log |
| `zeek:notice` | Notice Log |
| `zeek:weird` | Weird Log |

### Other Network
| Sourcetype | Product |
|---|---|
| `bluecoat:proxySG` | Broadcom ProxySG |
| `bluecoat:proxysg:access:syslog` | ProxySG Access (Syslog) |
| `bluecoat:proxysg:access:file` | ProxySG Access (W3C File) |
| `symantec:proxy:access` | Symantec Web Security Service |
| `sonicwall:firewall` | SonicWall Firewall |
| `sophos:utm` | Sophos UTM |
| `aruba:clearpass` | Aruba ClearPass NAC |
| `pulse:secure:vpn` | Ivanti/Pulse Secure VPN |
| `netscaler:ssl` | Citrix NetScaler |
| `radware:defensepro` | Radware DefensePro |
| `netscout:sightline` | NetScout Sightline |
| `netflow:log` | NetFlow (generic) |
| `coredns:log` | CoreDNS |
| `ms:dhcp` | Windows DHCP Server |
| `csv:generic_firewall` | Generic Firewall CSV |

---

## Infrastructure (39)

### VMware ESXi
| Sourcetype | Product |
|---|---|
| `vmware:esxi:vmkernel` | ESXi VMkernel Log |
| `vmware:esxi:hostd` | ESXi Hostd (Host Management) |
| `vmware:esxi:vpxa` | ESXi VPXA Agent (vCenter comms) |
| `vmware:esxi:fdm` | ESXi FDM (HA Agent) |
| `vmware:esxi:vobd` | ESXi VOBD (Hardware Events) |
| `vmware:esxi:shell` | ESXi Shell / SSH |
| `vmware:esxi:auth` | ESXi Auth Log |
| `vmware:esxi:storage` | ESXi Storage / SCSI |
| `vmware:esxi:vsan` | ESXi vSAN |
| `vmware:esxi:vmkwarning` | ESXi VMkernel Warnings |
| `vmware:esxi:syslog` | ESXi Remote Syslog |
| `vmware:vsphere:esx:syslog` | ESXi Syslog (TA-vmware) |

### VMware vCenter
| Sourcetype | Product |
|---|---|
| `vmware:vsphere:vcenter:syslog` | vCenter Syslog |
| `vmware:vsphere:vcenter:audit` | vCenter Audit Events |
| `vmware:vcenter:vpxd` | vCenter VPXD Main Service |
| `vmware:vcenter:eam` | vCenter ESX Agent Manager |
| `vmware:vcenter:rhttpproxy` | vCenter Reverse HTTP Proxy |
| `vmware:vcenter:sts` | vCenter SSO / STS |
| `vmware:vcenter:vpostgres` | vCenter Embedded PostgreSQL |

### VMware NSX
| Sourcetype | Product |
|---|---|
| `vmware:nsx:firewall` | NSX Distributed Firewall |
| `vmware:nsx:syslog` | NSX Manager Syslog |
| `vmware:nsx:audit` | NSX Audit Log |
| `vmware:nsx:ids` | NSX IDS/IPS |
| `vmware:nsx:intelligence` | NSX Intelligence |

### VMware Other
| Sourcetype | Product |
|---|---|
| `vmware:vsan:health` | vSAN Health Events |
| `vmware:horizon:syslog` | Horizon VDI |
| `vmware:aria:operations` | Aria Operations (vROps) |
| `vmware:aria:logs` | Aria Operations for Logs (vRLI) |
| `vmware:sddc:manager` | Cloud Foundation SDDC Manager |
| `vmware:workspace_one:audit` | Workspace ONE UEM / AirWatch |
| `vmware:workspace_one:events` | Workspace ONE Intelligence |

### Kubernetes
| Sourcetype | Product |
|---|---|
| `kube:apiserver:audit` | Kubernetes API Server Audit |
| `kube:container:log` | Kubernetes Container Logs |
| `kube:events` | Kubernetes Events |

### Docker
| Sourcetype | Product |
|---|---|
| `docker:events` | Docker Engine Events |
| `docker:container:logs` | Docker Container Logs (JSON driver) |
| `docker:daemon:log` | Docker Daemon Syslog |
| `docker:stats` | Docker Container Stats |
| `docker:registry:access` | Docker Registry / Harbor |

---

## Cloud (38)

### Amazon Web Services (17)
| Sourcetype | Product |
|---|---|
| `aws:cloudtrail` | CloudTrail |
| `aws:cloudtrail:digest` | CloudTrail Digest |
| `aws:cloudwatch` | CloudWatch |
| `aws:cloudwatch:ec2` | CloudWatch EC2 |
| `aws:cloudwatch:logs` | CloudWatch Logs |
| `aws:vpc:flow` | VPC Flow Logs |
| `aws:s3:access` | S3 Server Access |
| `aws:guardduty` | GuardDuty |
| `aws:securityhub` | Security Hub |
| `aws:config` | AWS Config |
| `aws:waf` | WAF Logs |
| `aws:inspector` | Inspector |
| `aws:elb:accesslogs` | ELB Access Logs |
| `aws:route53:logs` | Route53 DNS Logs |
| `aws:iam:accessadvisor` | IAM Access Advisor |
| `aws:sqs` | SQS |
| `awsfargate:log` | ECS Fargate |

### Microsoft Azure / Entra (10)
| Sourcetype | Product |
|---|---|
| `azure:aad:signin` | Azure AD Sign-In Logs |
| `azure:aad:audit` | Azure AD Audit Logs |
| `azure:aad:provisioning` | Azure AD Provisioning |
| `azure:activity` | Azure Activity Log |
| `azure:audit` | Azure Audit |
| `azure:eventhub` | Azure Event Hub |
| `azure:resource:graph` | Azure Resource Graph |
| `azure:securitycenter:alerts` | Microsoft Defender for Cloud |
| `azure:sentinel:incident` | Microsoft Sentinel Incidents |
| `ms:aad:riskyuser` | Azure AD Risky Users |
| `ms:aad:riskDetection` | Azure AD Risk Detections |

### Google Cloud Platform (5)
| Sourcetype | Product |
|---|---|
| `gcp:audit` | GCP Audit Log |
| `gcp:vpcflow` | GCP VPC Flow |
| `gcp:compute:firewall` | GCP Firewall |
| `gcp:dns:query` | GCP Cloud DNS |
| `gcp:iam:policy` | GCP IAM Policy |
| `gcp:pubsub:message` | GCP Pub/Sub |
| `gcp:securitycenter:findings` | Security Command Center |

### Google Workspace
| Sourcetype | Product |
|---|---|
| `google:workspace:admin` | Workspace Admin |
| `gsuite:activity` | Workspace Activity |

### Other Cloud
| Sourcetype | Product |
|---|---|
| `zoom:webhook` | Zoom Webhooks |

---

## Security (36)

### Identity & Access
| Sourcetype | Product |
|---|---|
| `okta:system` | Okta System Log |
| `okta:im2:log` | Okta Identity Engine |
| `okta:system:log:api` | Okta System Log API v1 |
| `cyberark:epv` | CyberArk EPV |
| `cyberarkpas:audit` | CyberArk PAS Audit |
| `delinea:sss:syslog` | Delinea Secret Server |
| `delinea:dpc:syslog` | Delinea Privilege Manager |
| `beyondtrust:pb` | BeyondTrust Privileged Access |
| `rsa:securid:syslog` | RSA SecurID |
| `sailpoint:identitynow:events` | SailPoint IdentityNow |
| `saviynt:audit` | Saviynt EIC |
| `pingfederate:audit` | PingFederate |
| `pingaccess:audit` | PingAccess |
| `hashicorp:vault:audit` | HashiCorp Vault |

### Threat Detection / SIEM
| Sourcetype | Product |
|---|---|
| `suricata:eve` | Suricata EVE JSON |
| `snort:log` | Snort IDS/IPS |
| `wazuh:alerts` | Wazuh SIEM Alerts |
| `ossec:alerts` | OSSEC/Wazuh (flat) |
| `extrahop:revealx:detection` | ExtraHop Reveal(x) |
| `misp:threat_intel` | MISP Threat Intelligence |
| `splunk:es:notable` | Splunk ES Notable Events |
| `stash` | Splunk ES Stash |

### Vulnerability Management
| Sourcetype | Product |
|---|---|
| `qualys:vmdr` | Qualys VMDR |
| `rapid7:nexpose` | Rapid7 Nexpose |
| `tenable:sc` | Tenable Security Center |
| `tenable:io:assets` | Tenable.io Assets |
| `snyk:vulnerabilities` | Snyk Vulnerabilities |

### DevSecOps
| Sourcetype | Product |
|---|---|
| `github:audit` | GitHub Enterprise Audit |
| `gitlab:audit` | GitLab Audit |

### Log Formats
| Sourcetype | Product |
|---|---|
| `cef` | Common Event Format (CEF) |
| `leef` | Log Event Extended Format (LEEF) |
| `elastic:ecs:json` | Elastic ECS (Filebeat) |
| `elastic:ndjson:export` | Elasticsearch NDJSON Export |
| `elastic:filebeat` | Elastic Filebeat |
| `elastic:winlogbeat` | Elastic Winlogbeat |

### Other
| Sourcetype | Product |
|---|---|
| `WinEventLog:Microsoft-Windows-Windows Defender/Operational` | Windows Defender |
| `imperva:securesphere` | Imperva SecureSphere WAF |

---

## Cisco (31)

### Firewalls
| Sourcetype | Product |
|---|---|
| `cisco:asa` | ASA / FTD Firewall |
| `cisco:ftd` | Firepower Threat Defense |
| `cisco:firepower` | Firepower / FMC |

### Routing & Switching
| Sourcetype | Product |
|---|---|
| `cisco:ios` | IOS / IOS-XE |
| `cisco:ios:show_log` | IOS Show Logging Output |
| `cisco:nx_os` | NX-OS |
| `cisco:catalyst` | Catalyst Switch |

### SD-WAN (11 sourcetypes)
| Sourcetype | Product |
|---|---|
| `cisco:sdwan:vmanage` | vManage (general) |
| `cisco:sdwan:vmanage:audit` | vManage Audit Log |
| `cisco:sdwan:vmanage:alarms` | vManage Alarms |
| `cisco:sdwan:vmanage:events` | vManage Events |
| `cisco:sdwan:vmanage:statistics` | vManage Statistics |
| `cisco:sdwan:vmanage:device` | vManage Device Inventory |
| `cisco:sdwan:vmanage:bfd` | BFD Sessions |
| `cisco:sdwan:vmanage:ipsec` | IPSec Statistics |
| `cisco:sdwan:vmanage:omp` | OMP Routes |
| `cisco:sdwan:vmanage:interface` | Interface Statistics |
| `cisco:sdwan:vedge` | vEdge Router |
| `cisco:sdwan:cedge` | cEdge (IOS-XE) Router |

### Security & Identity
| Sourcetype | Product |
|---|---|
| `cisco:ise` | Identity Services Engine |
| `cisco:acs` | ACS / ISE RADIUS |
| `cisco:duo:admin` | Duo Admin API |
| `cisco:duo:authentication` | Duo Authentication |
| `cisco:umbrella` | Umbrella DNS Security |
| `cisco:amp` | Secure Endpoint (AMP) |

### Infrastructure & Management
| Sourcetype | Product |
|---|---|
| `cisco:meraki` | Meraki |
| `cisco:wlc` | Wireless LAN Controller |
| `cisco:dnac` | DNA Center / Catalyst Center |
| `cisco:stealthwatch` | Secure Network Analytics |
| `cisco:tetration` | Secure Workload (Tetration) |
| `cisco:thousandeyes` | ThousandEyes |
| `cisco:ucs` | UCS Manager |
| `cisco:hyperflex` | HyperFlex HCI |
| `cisco:ciscosecure:email` | Secure Email (ESA/IronPort) |
| `cisco:sdwan:vmanage` | SD-WAN vManage (general syslog) |

---

## Windows (24)

| Sourcetype | Product |
|---|---|
| `WinEventLog:Security` | Security Event Log |
| `WinEventLog:System` | System Event Log |
| `WinEventLog:Application` | Application Event Log |
| `WinEventLog:Setup` | Setup Event Log |
| `WinEventLog:ForwardedEvents` | Forwarded Events |
| `WinEventLog:evtx` | EVTX Binary Format |
| `WinEventLog:Microsoft-Windows-Sysmon/Operational` | Sysmon |
| `WinEventLog:Microsoft-Windows-PowerShell/Operational` | PowerShell |
| `WinEventLog:Microsoft-Windows-Windows Defender/Operational` | Defender |
| `WinEventLog:Microsoft-Windows-Windows Firewall With Advanced Security/Firewall` | Windows Firewall |
| `WinEventLog:Microsoft-Windows-AppLocker/EXE and DLL` | AppLocker EXE/DLL |
| `WinEventLog:Microsoft-Windows-AppLocker/MSI and Script` | AppLocker MSI/Script |
| `WinEventLog:Microsoft-Windows-TaskScheduler/Operational` | Task Scheduler |
| `WinEventLog:Microsoft-Windows-WMI-Activity/Operational` | WMI Activity |
| `WinEventLog:Microsoft-Windows-TerminalServices-LocalSessionManager/Operational` | Terminal Services |
| `WinEventLog:Microsoft-Windows-Bits-Client/Operational` | BITS Client |
| `WinEventLog:Microsoft-Windows-DNS-Client/Operational` | DNS Client |
| `WinEventLog:Microsoft-Windows-CodeIntegrity/Operational` | Code Integrity |
| `WinEventLog:Microsoft-Windows-PrintService/Operational` | Print Service |
| `XmlWinEventLog:Security` | Security (XML/Syslog) |
| `XmlWinEventLog:System` | System (XML/Syslog) |
| `XmlWinEventLog:Microsoft-Windows-Sysmon/Operational` | Sysmon (XML) |
| `wineventlog:security:enhanced` | Security (Enhanced/JSON) |
| `elastic:winlogbeat` | Elastic Winlogbeat |

---

## Endpoint (23)

### CrowdStrike
| Sourcetype | Product |
|---|---|
| `crowdstrike:falcon:event` | Falcon Platform Events |
| `crowdstrike:fdr:json` | Falcon Data Replicator |
| `crowdstrike:telemetry:events` | Falcon Telemetry |

### Carbon Black (VMware)
| Sourcetype | Product |
|---|---|
| `carbonblack:edr` | Carbon Black EDR |
| `carbonblack:defense:json` | Carbon Black Cloud (Defense) |
| `carbonblack:cloud:alert` | Carbon Black Cloud Alerts |
| `carbonblack:cloud:endpoint.event` | Carbon Black Cloud Endpoint Events |

### SentinelOne
| Sourcetype | Product |
|---|---|
| `sentinelone` | SentinelOne EDR |
| `sentinelone:activity` | Activity Logs |
| `sentinelone:threat` | Threats |

### Other Endpoint
| Sourcetype | Product |
|---|---|
| `microsoft:defender_atp` | Microsoft Defender for Endpoint |
| `ms:o365:defender:atp` | Defender for Endpoint (O365) |
| `checkpoint:harmony:endpoint` | Check Point Harmony Endpoint |
| `cisco:amp` | Cisco Secure Endpoint (AMP) |
| `cylance:protect` | CylancePROTECT |
| `symantec:ep` | Symantec Endpoint Protection |
| `sophos:central` | Sophos Central |
| `trellix:epo` | Trellix ePO (McAfee) |
| `trendmicro:apex:cef` | Trend Micro Apex Central |
| `trendmicro:deep:security` | Trend Micro Deep Security |
| `osquery:syslog` | osquery Syslog |
| `osquery:result` | osquery Result |
| `santa:log` | Santa (macOS) |

---

## Email (13)

| Sourcetype | Product |
|---|---|
| `ms:o365:management` | Office 365 Management API |
| `ms:o365:exchange:messageTrace` | Exchange Message Trace |
| `ms:o365:dlp:all` | O365 DLP |
| `ms:exchange` | Exchange Server |
| `proofpoint:tap` | Proofpoint TAP |
| `proofpoint:pod:message` | Proofpoint PoD Message |
| `proofpoint:pod:maillog` | Proofpoint PoD Mail Log |
| `mimecast:siem` | Mimecast SIEM |
| `mimecast:siem:ttp` | Mimecast TTP |
| `mimecast:siem:receipt` | Mimecast Receipt |
| `barracuda:spamfirewall` | Barracuda Spam Firewall |
| `cisco:ciscosecure:email` | Cisco Secure Email (ESA) |

---

## Linux (9)

| Sourcetype | Product |
|---|---|
| `linux_secure` | `/var/log/secure` (RHEL/CentOS) |
| `linux_syslog` | Syslog |
| `linux_audit` | Linux Audit Log |
| `linux:auth` | `/var/log/auth.log` (Debian/Ubuntu) |
| `linux:audit:syslog` | Audit Daemon (syslog bridge) |
| `linux_cron` | Cron Log |
| `auditd:log` | auditd |
| `iptables:log` | iptables Firewall |
| `syslog` | Generic Syslog (RFC 5424/3164) |

---

## Web (9)

| Sourcetype | Product |
|---|---|
| `access_combined` | Apache/Nginx Combined Access Log |
| `apache:error` | Apache Error Log |
| `iis` | IIS Access Log (W3C) |
| `nginx:plus:kv` | Nginx Plus (Key-Value) |
| `haproxy:log` | HAProxy |
| `squid:access` | Squid Proxy |
| `tomcat:access` | Apache Tomcat |
| `traefik:access` | Traefik Proxy |
| `envoyproxy:access` | Envoy Proxy |

---

## Database (8)

| Sourcetype | Product |
|---|---|
| `mssql:error` | Microsoft SQL Server |
| `mysql:error` | MySQL |
| `postgresql:log` | PostgreSQL |
| `oracle:audit` | Oracle Unified Audit |
| `oracle:db:audit` | Oracle DB Audit |
| `mongodb:diag` | MongoDB Diagnostic |
| `elasticsearch:audit` | Elasticsearch Audit |
| `redis:log` | Redis |

---

## Middleware (6)

| Sourcetype | Product |
|---|---|
| `kafka:log` | Apache Kafka |
| `rabbitmq:log` | RabbitMQ |
| `activemq:log` | Apache ActiveMQ |
| `zookeeper:log` | Apache ZooKeeper |
| `ibmmq:errorlog` | IBM MQ |
| `nats:log` | NATS Server |

---

## Monitoring (6)

| Sourcetype | Product |
|---|---|
| `monitoring:nagios` | Nagios |
| `monitoring:prometheus` | Prometheus |
| `icinga:log` | Icinga2 |
| `pagerduty:webhooks` | PagerDuty |
| `snow:incident` | ServiceNow Incidents |
| `snow:audit` | ServiceNow Audit |

---

## Storage (3)

| Sourcetype | Product |
|---|---|
| `netapp:ontap:ems` | NetApp ONTAP EMS |
| `emc:vnx` | Dell EMC VNX/Unity |
| `rubrik:cdm` | Rubrik Cloud Data Management |

---

## OT/ICS (2)

| Sourcetype | Product |
|---|---|
| `claroty` | Claroty OT Security |
| `ot:generic:syslog` | Generic OT/ICS Syslog |

---

## Generic (1)

| Sourcetype | Product |
|---|---|
| `json_no_timestamp` | JSON without timestamp |

---

## Log Cleaning

Every signature includes automatic log cleaning — dirty lines (banners, headers, separators) are stripped before the file is routed to its landing zone. Cleaned files go to `landing/<sourcetype>/filename.log`. Stripped lines go to `landing/<sourcetype>/filename.noise.log`.

**Filter modes used across signatures:**

| Mode | Count | Examples |
|---|---|---|
| `line` | ~120 | Syslog, CEF, PAN CSV, auditd, Cisco IOS |
| `multiline/json_lines` | ~80 | CloudTrail, Azure AD, Okta, Suricata EVE |
| `multiline/json_object` | ~50 | GuardDuty, Carbon Black, VMware |
| `multiline/xml_event` | ~25 | Windows Event Log, EVTX |
| `multiline/zeek_tsv` | 8 | All Zeek logs |
| `multiline/iis` | 2 | IIS, ProxySG W3C |
| `passthrough` | ~42 | Complex formats without a reliable line filter |

See [README.md](README.md) for full cleaning documentation.
