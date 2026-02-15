1. Topologies are currently added as new items in networkgraph db in cosmos-gremlin. Telemetry and prompts should go to a telemetry db and prompts db in cosmos gremlin nosql and be instantiated in scenario specific containers. This will speed up loading time 
2. Scenario upload should have a timer so users can time the progress 
3. Can we have the graph api container logs stream to a third pane in the header? CUrrently we have graph topology and fabric container log stream in there. Let's get the graph API log stream there too.
4. Can we have a graph pause/unpause so that it stops moving whenever mouse over it? May have to check /home/hanchoong/projects/autonomous-network-demo/custom_skills/react-force-graph-2d for details
5. Lets have a sidebar on the right side to track interactions. Those interactions should be saved and retrieved and stored in cosmosdb-gremlin-nosql in a db called interactions. Timestamps and scenario name displayed along with the query used. When clicked on, the steps and final diagnosis should be displayed in the main UI. 
6. Let's create all the core DBs we will need in bicep, at azure provisioning stage, if we can. So we don't have to reinstantiate them. These are:

Cosmos-gremlin
networkgraph -> holds all graph data

cosmos-gremlin-nosql 
scenarios 
telemetry