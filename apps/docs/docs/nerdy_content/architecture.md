---
sidebar_position: 1
---

# Software Architecture

The backend of GOAT is making use of a Microservice architecture that is built using a diverse tech stack. The Backend of the GOAT platform is built using the following core technologies:

- [Python](https://www.python.org/)
- [PostgreSQL](https://www.postgresql.org/)
- [PostGIS](https://postgis.net/)
- [FastAPI](https://fastapi.tiangolo.com/)
- [Keycloak](https://www.keycloak.org/)
- [DuckDB / DuckLake](https://duckdb.org/)
- [Windmill](https://www.windmill.dev/)

To describe the software architecture the [C4 Model](https://c4model.com/) is used. The C4 Model is a hierarchical model that describes the software architecture on four different levels. The following sections will describe level 1 and level 2 of the C4 Model, which are context and containers.

## Contexts
![Context Diagram C4 Model](../../static/diagrams/out/context_v2.svg)

#### Web application
The client represents the application's user interface, comprising both a map view and a dashboard view. The dashboard serves multiple functions; it facilitates user account management, project creation, and oversees data management. In contrast, the map view is geared towards project execution, performance of analyses, and visualization and export of results, enabling users to interactively engage with their data.

#### Authentication
The authentication system is responsible for managing users, organizations, and groups. It is used to authenticate users and check their roles. 

#### Authorization
The authorization system takes charge of supervising permissions and subscriptions. Its principal function involves verifying whether a user possesses the requisite permissions to undertake a specific action, thereby maintaining robust control over application access and user activities.

#### GOAT Application
The GOAT application forms the heart of the GOAT platform. Its role includes managing projects, conducting analyses, and generating results. In addition to these duties, the application also performs analyses and accurately delivers the related data, making it a complete solution for data processing and interpretation.

## Containers

The following container diagram is a high-level overview of the different services used in GOAT. The containers are described in more detail in the following sections.

![Container Diagram C4 Model](../../static/diagrams/out/container_v2.svg)

### Web application 

#### React

#### Next.js 


### Authentication
Keycloak is an open-source solution, used for managing users and groups as well as organizations, with the help of the PhaseTwo extension. This tool identifies users and knows their roles, organization, and groups they belong to. Keycloak-related data, including those related to organizations, is stored in a PostgreSQL Database.

#### Keycloak API
The Keycloak API is a REST API that is used to manage users, groups, and organizations. The web application is directly interacting with the API to authenticate users. 

#### Keycloak Database
The Keycloak Database is a PostgreSQL Database that is used to store the Keycloak data. It is managed by the Keycloak system and we are not directly interacting with it. 

### Authorization 
The GOAT backend is comprised of several containers, with the authorization container serving as the central communication hub. The authorization API is written in Python using FastAPI. It is responsible for managing all incoming requests from the front end and communicating with other containers as necessary. Though authentication is handled in the authentication layer, within the authorization system lies the authorization mechanism. This involves verifying that a user possesses proper permissions and subscriptions (in SaaS installations) before granting access to the requested action. All related data is stored in a PostgreSQL database, accessed through SQLAlchemy.

#### Authorization and Accounts API

This is a REST API, crafted in Python using FastAPI. The API possesses dual functionalities. Its primary role is to authenticate users by validating their permissions, subscriptions, and roles, effectively functioning as an API gateway. This feature is crucial for protecting the GOAT application API from unauthorized access. Upon successful authorization of a user for a requested service, the API forwards the request to the GOAT API.

Secondly, this API provides access to both user and organization data, managing the distribution of content among various groups. It directly interacts with the accounts database, employing SQLAlchemy to extract the necessary data.
In addition to this, the API communicates with the Keycloak API, facilitated by a library known as 'python-keycloak'. This interaction negates the need for direct API access. Upon receiving the user token, it is used to retrieve user details and verify their roles.

#### Authorization and Accounts Database

We utilize a PostgreSQL database to store detailed user, organization, and group data, which falls beyond the scope of Keycloak. This database also holds references to content uploaded through the GOAT application, tracking its sharing across various groups. Furthermore, it carefully manages user subscriptions and the linked regions, delineating the geographical boundaries for each subscription.

### GOAT Application

#### GOAT Core API
The GOAT Core API, developed using Python and FastAPI, serves as the central core of the application. It takes on the critical tasks of managing projects, folders, scenarios, and content metadata. It maintains direct interaction with the Application Database and exposes the endpoints the client uses for project and account management.

#### GEO API
The GEO API is a Python/FastAPI service that implements the OGC API Features and Vector Tiles specifications. It serves user layers and analysis outputs directly out of the DuckLake analysis database, so tile and feature requests stay fast and isolated from long-running analytics jobs.

#### Processes API
The Processes API is a Python/FastAPI service implementing the OGC API Processes specification. It exposes the analytical capabilities of GOAT as standardized processes, validates inputs, manages jobs, and dispatches the work to the workflow engine.

#### Workflow Engine (Windmill + goatlib)
Heavy analyses run on [Windmill](https://www.windmill.dev/), which acts as the workflow and job-execution engine. The Windmill workers ship with `goatlib` pre-installed — the shared Python library that contains all of GOAT's analytical features: accessibility and isochrone analyses, routing for car/walking/cycling/public transport, indicator calculations, scenario logic, and data import/export. Every analytical tool is registered as a Windmill job and reads/writes directly from the DuckLake analysis database. This collapses what used to be several dedicated routing services into a single, horizontally scalable execution layer.

#### Application Database

The Application Database is a PostgreSQL database with the PostGIS extension. It stores everything needed to operate GOAT outside of the bulk geospatial payload: user accounts, organizations, projects, folders, layer metadata, scenarios, jobs, and subscriptions.

#### Analysis Database (DuckLake)

User layers and the outputs of analytical jobs are stored in a [DuckLake](https://ducklake.select/) catalog backed by Parquet on object storage and queried with DuckDB. This separation — metadata in PostgreSQL, bulk geospatial data in DuckLake — lets the GEO API serve features and tiles efficiently while the workflow engine reads and writes the same data for analyses.
