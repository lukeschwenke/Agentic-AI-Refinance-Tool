"""Generates src/frontend/images/arch_diagram_v3.png.

Re-run whenever the architecture changes:
    pip install diagrams && apt-get/brew install graphviz
    python docs/generate_arch_diagram.py
then copy arch_diagram_v3.png into src/frontend/images/.
"""
from diagrams import Diagram, Cluster, Edge
from diagrams.aws.network import Route53, InternetGateway
from diagrams.aws.compute import EC2ElasticIpAddress, Lambda, ECR
from diagrams.aws.database import Dynamodb
from diagrams.aws.integration import SNS, Eventbridge
from diagrams.onprem.network import Caddy, Internet
from diagrams.onprem.container import Docker
from diagrams.onprem.client import Users, User

graph_attr = {
    "fontsize": "22",
    "pad": "0.5",
    "splines": "spline",
    "nodesep": "0.7",
    "ranksep": "1.0",
    "dpi": "140",
}

with Diagram(
    "RefiAI on AWS — EC2 + Docker, HTTPS via Caddy + Let's Encrypt",
    filename="arch_diagram_v3",
    direction="LR",
    show=False,
    graph_attr=graph_attr,
):
    users = Users("Users")
    letsencrypt = Internet("Let's Encrypt\n(ACME CA)")
    ext_apis = Internet("Live market data\nOpenAI · Tavily\nCNBC · Credit Union")
    subscriber = User("Email\nsubscriber")

    with Cluster("AWS Cloud (us-east-1)"):
        route53 = Route53("Route 53\nrefi-agentic-ai\n.lukeschwenke.com")
        ecr = ECR("ECR\napp image")
        dynamo = Dynamodb("DynamoDB\nrequest logs +\nrate-limit counters\n(5/IP/day · 25/day global)")

        with Cluster("Daily email"):
            schedule = Eventbridge("EventBridge\ndaily schedule")
            fn = Lambda("Lambda\nrefi check")
            sns = SNS("SNS topic")

        with Cluster("VPC"):
            igw = InternetGateway("Internet\nGateway")
            with Cluster("Public subnet — SG: 80/443 open (8000 for API)"):
                eip = EC2ElasticIpAddress("Elastic IP")
                with Cluster("EC2 — Docker network: refi_network"):
                    caddy = Caddy("Caddy proxy  :80/:443\nTLS termination,\nauto-renewed cert")
                    ui = Docker("Streamlit UI\n:3000 (internal)")
                    api = Docker("FastAPI backend\n:8000 — LangGraph\nagents")

    # user traffic
    users >> Edge(label="DNS lookup", style="dashed") >> route53
    route53 >> Edge(label="A record", style="dashed") >> eip
    users >> Edge(label="HTTPS :443\n(HTTP :80 → redirect)") >> igw >> eip >> caddy
    caddy >> Edge(label="reverse proxy") >> ui
    ui >> Edge(label="POST /refinance_agent/\nrecommendation (+ client IP)") >> api

    # certs
    caddy >> Edge(label="ACME cert\nissue / renew", style="dashed", color="darkgreen") >> letsencrypt

    # backend dependencies
    api >> Edge(label="agents fetch\nlive rates") >> ext_apis
    api >> Edge(label="log requests +\nenforce daily limits") >> dynamo

    # deploy path
    ecr >> Edge(label="docker pull\n(on deploy)", style="dotted") >> api

    # scheduled email
    schedule >> fn
    fn >> Edge(label="POST :8000\n(skips demo limits)") >> api
    fn >> Edge(label="publish\nrecommendation") >> sns
    sns >> Edge(label="email") >> subscriber
