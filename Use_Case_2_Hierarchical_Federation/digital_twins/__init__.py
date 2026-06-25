"""
digital_twins — Digital twin definitions for the Japanese plum orchard

Each subdirectory represents one digital twin (trunk, leaf, tree, sprinkler,
farm) and contains:
  - init/       BaSyx AAS shell + submodel initialisation script (bash + curl)
  - service/    Business logic service (Flask) with BaSyx REST API integration

All digital twins operate purely in-memory with no persistent databases.

Dependencies shared across services live in the shared/ package.
"""
