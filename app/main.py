from aiohttp import ClientSession
from dotenv import load_dotenv
load_dotenv()
import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from .router import router
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 애플리케이션이 시작될 때 실행되는 코드
    app.state.session = ClientSession()
    app.state.response_queues = {}
    app.state.convos = {}
    
    # Lifespan 관리 코드
    try:
        yield
    finally:
        # 애플리케이션 종료 시 실행되는 코드
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

# @app.middleware("http")
# async def authentication(request: Request, call_next):
#     if request.url.path == '/twilio/twiml/start':
#         logging.info("Middleware executed for requested endpoint: '/twilio/twiml/start'")
#         logging.info("Endpoint: @app.middleware('http')")
        
#         # Read and store the request body as bytes
#         # Store the body bytes so it can be reused later in the request
#         body_bytes = await request.body()
#         request._body = body_bytes

#         # Convert the bytes into a form-like object (FormData)
#         form_data = await request.form()
#         caller = form_data.get('Caller')
#         print(f'Form data: {caller}')

#         authenticated = True
#         if authenticated:
#             # Pass the request to the next process (router or another middleware)
#             response = await call_next(request)
#             return response
#         else:
#             logging.error('')
#             return
    
#     else:
#         response = await call_next(request)
#         return response

app.include_router(router.router)
