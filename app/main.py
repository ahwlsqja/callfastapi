from aiohttp import ClientSession
import logging

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.router import router
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.session = ClientSession()
    app.state.response_queues = {}
    app.state.convos = {}

    try:
        yield
    finally:
        await app.state.session.close()

app = FastAPI(
    title='Voip ML Server API',
    summary='API Endpoints for ML Calls',
    openapi_tags=[
        router.metadata,
    ],
    docs_url='/',
    lifespan=lifespan,
)

origins = ['*']
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

@app.middleware("http")
async def authentication(request: Request, call_next):
    if request.url.path == '/twilio/twiml/start':
        logging.info("Middleware executed for requested endpoint: '/twilio/twiml/start'")
        logging.info("Endpoint: @app.middleware('http')")
        
        body_bytes = await request.body()
        request._body = body_bytes

        form_data = await request.form()
        caller = form_data.get('Caller')
        print(f'Form data: {caller}')

        authenticated = True
        if authenticated:
            response = await call_next(request)
            return response
        else:
            logging.error('')
            return
    
    else:
        response = await call_next(request)
        return response

app.include_router(router.router)
