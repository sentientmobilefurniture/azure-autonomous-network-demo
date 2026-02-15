# Fabric Integration Plan

## Objective 

Add Fabric Ontology as an alternative graph backend to cosmosDB with gremlin
Fabric will be manually provisioned by user, who only has to provide necessary IDs and such.
Requirements:
1. Manually provide a Fabric workspace ID 
2. Read all available ontologies and provide as a list for graph explorer agent 
3. Select the desired ontology 
4. Read all available eventhouses and provide as a list for telemetry agent.
5. Query graph to retrieve topology and display it using the graph visualizer module 
6. Graph Explorer and Graph telemetry agent will be bound with Fabric data connection - So a connection to the fabric workspace must be created
7. In Data sources settings menu... Have a checkbox. Add a first tab basically to choose which backend will be used. To choose whether using a cosmosDB backend or fabric backend. Clicking it will grey out the cosmosDB tabs and ungrey the fabric tab. In total there are four tabs now.
8. Agents will be able to query the fabric ontology freely. 

Likely, most of the relevant information will be present in /home/hanchoong/projects/autonomous-network-demo/fabric_implementation_references

## Implementation plan