import time
import requests
import json
import requests
import sys
import io
import os
import pandas as pd
import base64
from datetime import datetime
from pymongo import MongoClient
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import (Mail, Attachment, FileContent, FileName, FileType, Disposition, To)
from collections import defaultdict
from dotenv import load_dotenv
from telegram import Bot


class LogFile(io.TextIOWrapper):
    def write(self, s):
        timestamp = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
        super().write(f"{timestamp} {s}")


class TestSaldos:
    def __init__(self):
        load_dotenv()
        self.log_file = open("output.log", "a")
        sys.stdout = LogFile(self.log_file.buffer)
        sys.stderr = LogFile(self.log_file.buffer)
        self.log_file = open("output.log", "a")
        sys.stdout = LogFile(self.log_file.buffer)
        sys.stderr = LogFile(self.log_file.buffer)
        options = webdriver.ChromeOptions()
        options.add_argument("--ignore-certificate-errors")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--remote-debugging-port=9222")
        options.add_argument("--headless")
        options.add_argument("--log-level=3")  # Deshabilitar el registro del navegador
        self.driver = webdriver.Chrome(options=options)
        self.vars = {}
    ##defino los variables cuotas 1 rechazada, cuota 1 renunciada, cuota 1 activa, cuota 0 rechazada, cuota 0 renunciada, cuota 0 activa para poder enviarle el estado del mensaje
        self.cuotaRechazada = 0
        self.cuotaRenunciada = 0
        self.cuotaActiva = 0
        self.cuotaCobrada = 0
        self.cuotaBaja = 0
        self.cuotaSinInformacion = 0
    #funcion para volver a 0 las variables de las cuotas
    def resetCuotas(self):
        self.cuotaRechazada = 0
        self.cuotaRenunciada = 0
        self.cuotaActiva = 0
        self.cuotaCobrada = 0
        self.cuotaBaja = 0
        self.cuotaSinInformacion = 0
    def __del__(self):
        self.log_file.close()

    def setup_method(self, method):
        self.driver = webdriver.Chrome()
        self.vars = {}

    def teardown_method(self, method):
        self.driver.quit()

    def wait_for_window(self, timeout=2):
        time.sleep(round(timeout / 1000))
        wh_now = self.driver.window_handles
        wh_then = self.vars["window_handles"]
        if len(wh_now) > len(wh_then):
            return set(wh_now).difference(set(wh_then)).pop()

    def postZohoToken(self):
        ZOHO_CLIENT_ID = os.environ.get("ZOHO_CLIENT_ID")
        ZOHO_CLIENT_SECRET = os.environ.get("ZOHO_CLIENT_SECRET")
        ZOHO_REFRESH_TOKEN = os.environ.get("ZOHO_REFRESH_TOKEN")
        url = "https://accounts.zoho.com/oauth/v2/token"
        headers = {"content-Type": "application/x-www-form-urlencoded"}
        data = {
            "client_id": ZOHO_CLIENT_ID,
            "client_secret": ZOHO_CLIENT_SECRET,
            "refresh_token": ZOHO_REFRESH_TOKEN,
            "grant_type": "refresh_token",
        }
        response = requests.post(url, data=data, headers=headers)
        access_token = response.json()["access_token"]

        # Conectar a la base de datos MongoDB utilizando el URI de conexión SRV
        client = MongoClient(
            os.environ.get("MONGO_URI")
        )
        db = client[os.environ.get("MONGO_DB")]
        collection = db[os.environ.get("MONGO_COLLECTION")]

        # Guardar el access_token en la base de datos
        collection.insert_one(
            {"access_token": access_token, "timestamp": datetime.now()}
        )
        # print(response.json())
        #print("Access token guardado en la base de datos")
        return response.json()

    def getZohoToken(self):
        # Conectar a la base de datos MongoDB utilizando el URI de conexión SRV
        client = MongoClient(
            os.environ.get("MONGO_URI")
        )
        db = client[os.environ.get("MONGO_DB")]
        collection = db[os.environ.get("MONGO_COLLECTION")]

        # obtener el ultimo access token de la db creado
        access_token = collection.find().sort("_id", -1).limit(1)[0]["access_token"]
        # guardar access token en variable de entorno
        # print("Access token obtenido de la base de datos: ")
        return access_token


    def getAllZohoRecords(self, cuota):
        # Solicitar el access token de zoho
        access_token = self.getZohoToken()
        all_records = []
        limit = 200
        urls = ['https://creator.zoho.com/api/v2/autocredito/autocredito/report/Bot_C{cuota}?from={offset}&limit={limit}']
        
        for url in urls:
            offset = 1
            while True:
                formatted_url = url.format(offset=offset, limit=limit, cuota=cuota)
                headers = {"Authorization": "Zoho-oauthtoken " + access_token}
                response = requests.get(formatted_url, headers=headers)
                #print(headers)
                #print(formatted_url)
                #print(response.json())
                try:
                    response_json = response.json()
                except json.JSONDecodeError:
                    print("Error al decodificar la respuesta JSON:", response.text)
                    break
                
                if response_json.get("code") == 3000:
                    records = response_json.get("data")
                    all_records.extend(records)
                    
                    if len(records) < limit:
                        break
                        
                    offset += limit
                    
                elif response_json.get("code") == 1030 or response_json.get("code") == 2948:
                    #print("Access token expirado, se esta obteniendo uno nuevo...")
                    self.postZohoToken()
                    records = self.getAllZohoRecords(cuota)
                    return records
                    
                elif response_json.get("code") == 4000:
                    # terminar ejecucion del script por el limite de api de zoho
                    print("Limite de API de Zoho alcanzado")
                    print(response.json())
                    exit()
                elif response_json.get("code") == 2945:
                    self.postZohoToken()
                    records = self.getAllZohoRecords(cuota)
                    return records
                else:
                    break
        
        unique_records = []
        for record in all_records:
            if record not in unique_records:
                unique_records.append(record)
        all_records = unique_records
        #self.saveRecordsToExcel(all_records, "records.xlsx")
        print("Cantidad de registros: ", len(all_records))
        return all_records
          
    def saveRecordsToExcel(self,records, filename):
        df = pd.DataFrame(records)
        df.to_excel(filename, index=False)
    
    def getOneZohoRecord(self, id):
        access_token = self.getZohoToken()
        
        # URL de la API de Zoho creator
        url = "https://creator.zoho.com/api/v2/autocredito/autocredito/report/Copy_of_Reporte_de_venta_Organizadores?criteria=(ID={})".format(
            id
        )
        headers = {"Authorization": "Zoho-oauthtoken " + access_token}
        response = requests.get(url, headers=headers)
        if response.json().get("code") == 3000:
            hayRegistros = True
            datos = {
                "dni": response.json().get("data")[0]["DNI"],
                "nombre": response.json()
                .get("data")[0]["Nombre_y_apellido_cliente"]
                .upper(),
                "organizador": response.json()
                .get("data")[0]["Organizador_nuevo"]
                .upper(),
                "productor": response.json().get("data")[0]["Productor"].upper(),
                "nacimiento": response.json().get("data")[0]["Fecha_de_nacimiento"],
                "valorNominal": response.json().get("data")[0]["Valor_nominal"],
                "ss": response.json().get("data")[0]["Numero_de_SS"],
                "campana": response.json().get("data")[0]["Campa_a"],
            }
            # print(datos)
            return datos
        elif response.json().get("code") == 1030 or response.json().get("code") == 2948:
            print("El access token ha expirado, se procede a obtener uno nuevo")
            self.postZohoToken()
            response = self.getOneZohoRecord(id)
           
            # print(datos)
            return response
        else:
            hayRegistros = False
            print("No hay registros")
            # print(response.json())
            return hayRegistros

    def patchZohoRecord(self, id, cuota, estado, motivo, sorteo,no=None ):
        access_token = self.getZohoToken()
        data = {None}
        fecha = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        url = "https://creator.zoho.com/api/v2/autocredito/autocredito/report/Copy_of_Reporte_de_venta_Organizadores/{}".format(
            id
        )
        headers = {"Authorization": "Zoho-oauthtoken " + access_token}
        if estado == "Cobrado":
            self.cuotaCobrada += 1
            if cuota == 0 or cuota == '0':
                if sorteo == 0 or sorteo == '0' or sorteo == '' or sorteo == None:
                    data = {
                    "data": {"Pago_saldo_0": "Pagado - Sin Nro", "Pago_saldo_1":"Pendiente", "Nro_de_Sorteo": 000, "fecha_actualizacion_saldos": fecha}
                }
                else:
                    data = {
                        "data": {
                            "Pago_saldo_0": "Pagado",
                            "Pago_saldo_1":"Pendiente",
                            "Nro_de_Sorteo": sorteo,
                            "fecha_actualizacion_saldos": fecha,
                        }
                    }
            elif cuota == 1:
                data = {
                    "data": {
                        "Pago_saldo_1": "Pagado",
                        "Nro_de_Sorteo": sorteo,
                        "fecha_actualizacion_saldos": fecha,
                    }
                }
            else:
                ##data se arma dinamico con la cuota
                data = {
                    "data": {
                             f"Pago_saldo_{cuota}": "Pagado",
                             "fecha_actualizacion_saldos": fecha}
                }
        elif estado == "Rechazado":
            self.cuotaRechazada += 1
            if cuota == 0:
                data = {
                    "data": {
                        "Pago_saldo_0": "Rechazado",
                        "Motivo_renuncia_saldo": motivo,
                        "Pago_saldo_1": "Rechazo - C0",
                        "fecha_actualizacion_saldos": fecha,
                    }
                }
            elif cuota == 1:
                data = {
                    "data": {
                        "Pago_saldo_1": "Rechazado",
                        "Motivo_renuncia_saldo": motivo,
                        "fecha_actualizacion_saldos": fecha,
                    }
                }
            else:
                data = {
                    "data": {
                             f"Pago_saldo_{cuota}": "Rechazado",
                             "fecha_actualizacion_saldos": fecha}
                }
        elif estado == "Renunciado":
            self.cuotaRenunciada += 1
            if cuota == 0:
                data = {
                    "data": {
                        "Pago_saldo_0": "Renunciado",
                        "Pago_saldo_1": "Renunciado",
                        "Motivo_renuncia_saldo": motivo,
                        "fecha_actualizacion_saldos": fecha,
                    }
                }
            elif cuota == 1:
                data = {
                    "data": {
                        "Pago_saldo_1": "Renunciado",
                        "Motivo_renuncia_saldo": motivo,
                        "fecha_actualizacion_saldos": fecha,
                    }
                }
            else:
                data = {
                    "data": {
                             f"Pago_saldo_{cuota}": "Renunciado",
                             "Motivo_renuncia_saldo": motivo,
                             "fecha_actualizacion_saldos": fecha}
                }
        elif estado == "Activo":
            self.cuotaActiva += 1
            if cuota == 0:
                data = {
                    "data": {
                        "fecha_actualizacion_saldos": fecha,
                    }
                }
            elif cuota == 1:
                data = {
                    "data": {
                        "fecha_actualizacion_saldos": fecha,
                    }
                }
            else:
                data = {
                    "data": {
                             "fecha_actualizacion_saldos": fecha
                             }
                }
        elif estado == "Baja":
            self.cuotaBaja += 1
            if cuota == 0 or cuota == '0':
                data = {
                    "data": {
                        "Pago_saldo_0": "Baja",
                        "Motivo_renuncia_saldo": motivo,
                        "Pago_saldo_1": "Baja",
                        "fecha_actualizacion_saldos": fecha,
                    }
                }
            elif cuota == 1:
                data = {
                    "data": {
                        "Pago_saldo_1": "Baja",
                        "Motivo_renuncia_saldo": motivo,
                        "fecha_actualizacion_saldos": fecha,
                    }
                }
            else:
                data = {
                    "data": {
                             f"Pago_saldo_{cuota}": "Baja",
                             "Motivo_renuncia_saldo": motivo,
                             "fecha_actualizacion_saldos": fecha}
                }
        elif estado == "Sin informacion":
            self.cuotaSinInformacion += 1
            data = {
                    "data": {
                        "fecha_actualizacion_saldos": fecha,
                    }
                }
        elif estado == "Incompleto":
            data = {
                "data": {
                    "Estado": "Rechazada suscripcion digital",
                }
            }
        #evito que data se envio vacio
        #print(data)
        if data != {None}:
            #print(data)
            json_data = json.dumps(data)
            response = requests.patch(url, headers=headers, data=json_data)
            print(response.json())
            if response.json().get("code") == 1030 or response.json().get("code") == 2948:
                print("Token expirado, se esta obteniendo uno nuevo...")
                self.postZohoToken()
                access_token = self.getZohoToken()
                response = requests.patch(url, headers=headers, data=json_data)
                print(response.json())
            elif response.json().get("code") == 2945:
                print("Token expirado, se esta obteniendo uno nuevo...")
                self.postZohoToken()
                access_token = self.getZohoToken()
                response = requests.patch(url, headers=headers, data=json_data)
                print(response.json()) 
        else:
            print("No se envio nada, data vacio")
       

    def get_records_from_zoho(self, url, headers, limit):
        records = []
        offset = 0
        while True:
            params = {
                "from": offset,
                "limit": limit
            }
            try:
                response = requests.get(url, headers=headers, params=params)
                data = response.json()
                if "code" in data and data["code"] == 1030 or data["code"] == 2948:
                    # Renovar el token y volver a intentar
                    self.postZohoToken()
                    access_token = self.getZohoToken()
                    headers["Authorization"] = "Zoho-oauthtoken " + access_token
                    response = requests.get(url, headers=headers, params=params)
                    data = response.json()
                records.extend(data["data"])
            except requests.exceptions.RequestException as e:
                print(f"Error al obtener datos de Zoho Creator: {e}")
                break

            if len(data["data"]) < limit:
                break
            offset += limit
        return records

    def enviarMsjInicio(self,estado,chequeos,cuota):
        fecha = datetime.now().strftime("%d/%m/%Y")
        url = os.environ.get("TELEGRAM_URL")
        data = {"chat_id": os.environ.get("TELEGRAM_GROUP_ID")}
        if estado == "inicio":
            msj = "En el dia: {fecha}, se inicio el control de saldos Cuota: {cuota}. Datos a chequear: {chequeos}".format(fecha=fecha,cuota=cuota,chequeos=chequeos)
        elif estado == "fin":
            msj = "En el dia: {fecha}, se finalizo el control de saldos Cuota: {cuota}. Total chequeos: {chequeos}".format(fecha=fecha,cuota=cuota,chequeos=chequeos)
        data["text"] = msj
        response = requests.post(url, data=data)
        print(response.json())
    
    def enviarMsjResumenCuota(self,cuota):
        fecha = datetime.now().strftime("%d/%m/%Y")
        url = os.environ.get("TELEGRAM_URL")
        data = {"chat_id": os.environ.get("TELEGRAM_GROUP_ID")}
        msj = f"Cuota: {cuota} - Rechazadas: {self.cuotaRechazada} - Renunciadas: {self.cuotaRenunciada} - Activas: {self.cuotaActiva} - Cobradas: {self.cuotaCobrada} - Bajas: {self.cuotaBaja} - Sin informacion: {self.cuotaSinInformacion}"
        data["text"] = msj
        response = requests.post(url, data=data)
        print(response.json())   
    ##FUNCION PARA CREAR EL ARCHIVO DE EXCEL 
    def create_excel_file(self, records):
        df = pd.DataFrame(records)
        fecha_hoy = datetime.now().strftime('%d-%m-%Y')
        nombre_archivo = f"Rechazadas - {fecha_hoy}.xlsx"
        with pd.ExcelWriter(nombre_archivo) as writer:
            df.to_excel(writer, index=False, sheet_name="Rechazadas")
        return nombre_archivo
    
    def send_email_with_attachment(self, sendgrid_api_key, from_email, to_emails, subject, html_content, attachment_filename):
        message = Mail(
            from_email=from_email,
            to_emails=to_emails,
            subject=subject,
            html_content=html_content
        )

        with open(attachment_filename, "rb") as f:
            data = f.read()

        encoded_file = base64.b64encode(data).decode()

        attachment = Attachment()
        attachment.file_content = FileContent(encoded_file)
        attachment.file_type = FileType("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        attachment.file_name = FileName(attachment_filename)
        attachment.disposition = Disposition("attachment")
        message.attachment = attachment

        try:
            sendgrid_client = SendGridAPIClient(sendgrid_api_key)
            response = sendgrid_client.send(message)
            print(response.status_code)
        except Exception as e:
            print(f"Error al enviar correo electrónico con SendGrid: {e}")
    
    def enviarRechazos(self):
        self.postZohoToken()
        access_token = self.getZohoToken()
        url = "https://creator.zoho.com/api/v2/autocredito/autocredito/report/Rechazos_Bot"
        headers = {"Authorization": "Zoho-oauthtoken " + access_token}
        
        records = self.get_records_from_zoho(url, headers, 200)
        
        fecha_hoy = datetime.now().strftime('%d-%m-%Y')
        
        nombre_archivo = self.create_excel_file(records)
        
        from_email=os.environ.get("SENDGRID_FROM_EMAIL")
        to_emails=[To('fernando@grupogf2.com.ar'),To('gonzalo.pero@grupogf2.com.ar'),To('florencia.pero@autocredito.net.ar'),To('emmanuel.aleman@autocredito.net.ar'),To('camila.trimarchi@autocredito.net.ar')]
        subject=f"Rechazadas - {fecha_hoy}"
        html_content="<strong>Se adjuntan los saldos rechazados</strong>"
        
        sendgrid_api_key=os.environ.get("SENDGRID_API_KEY")
        #print(sendgrid_api_key)
        #print(from_email)
        #print(to_emails)
        self.send_email_with_attachment(sendgrid_api_key, from_email, to_emails, subject, html_content, nombre_archivo)

    def control(self, cuota):
        #es una version mejorada y mas rapida del metodo test_saldos
        self.vars["usuario"] = os.environ.get("AUTOGESTION_USER")
        self.vars["password"] = os.environ.get("AUTOGESTION_PASSWORD")
        print("Inicio de control de saldos C" + str(cuota))
        records = self.getAllZohoRecords(cuota)
        totalRecords = len(records)
        totalChequeos = 0
        if records == 'expired':
            print("El access token ha expirado, se procede a obtener uno nuevo")
            self.postZohoToken()
            self.control(cuota)
        #enviar mensaje al inicio del control
        self.enviarMsjInicio("inicio",totalRecords,cuota)
        for record in records:
            self.vars["id"] = record['ID']
            self.vars["ss"] = record['SS_completa']
            ##OBTENER EL VALRO PREVIO A / DE LA SS
            self.vars["nro_pre"] = self.vars["ss"].split("/", 1)[0]
            self.vars["nro_ingres"] = self.vars["ss"].split("/", 1)[1]
            self.driver.get("https://agencias.autocredito.com/extranet/agencias/consultas/datos.asp?nro_ingres={}".format(self.vars["ss"]))
            self.vars["isLogin"] = len(
                self.driver.find_elements(By.XPATH, "//input[@value='aceptar']")
            )
            # print("isLogin: {isLogin}".format(isLogin=self.vars["isLogin"]))
            if self.vars["isLogin"] == 1:
                # print("Inicio de sesion Autogestion")
                self.driver.find_element(By.NAME, "usu").send_keys(self.vars["usuario"])
                self.driver.find_element(By.NAME, "psw").send_keys(
                    self.vars["password"]
                )
                self.driver.find_element(By.XPATH, "//input[@value='aceptar']").click()
                self.driver.get(
                    "https://agencias.autocredito.com/extranet/agencias/consultas/datos.asp?nro_ingres={}".format(
                        self.vars["ss"]
                    )
                )
            # hacer una pausa de 5 segundos
            time.sleep(3)
            try:
                self.vars["estado"] = self.driver.find_element(
                By.XPATH, "//tr[33]/td[2]"
            ).text
            except:
                self.vars["estado"] = "Sin informacion"
            try:
                self.vars["nroSorteo"] = self.driver.find_element(
                By.XPATH, "//tr[5]/td[2]"
            ).text
            except:
                self.vars["nroSorteo"] = 0
            self.vars["principal"] = self.driver.current_window_handle
            print(
                "SS: {ss}, estado: {estado}".format(
                    ss=self.vars["ss"], estado=self.vars["estado"]
                )
            )
            if self.vars["estado"] == "Activo":
                self.driver.get(
                    "https://agencias.autocredito.com/extranet/agencias/consultas/ctacte.asp?nro_pre={nro_pre}&nro_ingres={nroIngres}".format(nro_pre=self.vars["nro_pre"], nroIngres=self.vars["nro_ingres"])
                )
                self.vars["countLinea"] = len(
                    self.driver.find_elements(By.XPATH, "//table[2]/tbody/tr")
                )
                if self.vars["countLinea"] > 2:
                    start_row = 4
                    end_row = self.vars['countLinea'] - 2
                    rows = self.driver.find_elements(By.XPATH, f"//table[2]/tbody/tr[position()>={start_row} and position()<={end_row}]")
                    sums = defaultdict(int)
                    fechas = defaultdict(int)
                    result = defaultdict(dict)
                    for i, row in enumerate(rows, start=start_row):
                        first_cell = row.find_element(By.XPATH, "./td[1]")
                        cuotaRow = first_cell.text.strip()
                        fifth_cell = row.find_element(By.XPATH, "./td[5]")
                        fecha_pago = row.find_element(By.XPATH, "./td[6]").text.strip()
                        countFechaPago = len(fecha_pago)
                        fechas[cuotaRow] += countFechaPago
                        imp_pagado = float(fifth_cell.text.replace('$', '').replace('.', '').replace(',', '.'))
                        sums[cuotaRow] += imp_pagado
                        tenth_cell = row.find_element(By.XPATH, "./td[10]")
                        link = tenth_cell.find_elements(By.XPATH, './/a[text()="ver motivo"]')
                        estado = ''
                        #poner estado solo si la fecha de pago existe
                        if link and not fechas[cuotaRow]:
                            estado = 'rechazado'
                        elif fecha_pago == '' or fecha_pago:
                            estado = 'activo' 
                        print(f"cuotaRow: {cuotaRow}, cuota: {cuota}, fecha pago: {fecha_pago}, estado: {estado}")
                        if estado == 'rechazado' and not result[cuotaRow].get('motivo'):
                            self.vars["window_handles"] = self.driver.window_handles
                            self.driver.find_element(
                                By.XPATH,
                                f"//table[2]/tbody/tr[{i}]/td[10]/a",
                            ).click()
                            self.vars["rechazoVentana"] = self.wait_for_window(5000)
                            self.driver.switch_to.window(self.vars["rechazoVentana"])
                            codigo_rechazo = self.driver.find_element(
                                By.XPATH, "//tr[2]/td"
                            ).text
                            self.driver.close()
                            self.driver.switch_to.window(self.vars["principal"])
                        else:
                            codigo_rechazo = ''
                        #solo ingresar si cuotaRow ES IGUAL O MAYOR A cuota
                        if int(cuotaRow) >= int(cuota):
                            result[cuotaRow] = {'cuota': cuotaRow, 'importe': f"${sums[cuotaRow]:,.2f}", 'estado': estado or result[cuotaRow].get('estado', ''), 'motivo': codigo_rechazo or result[cuotaRow].get('motivo', ''), 'id': self.vars['id'], 'ss': self.vars['ss'], 'nroSorteo': self.vars['nroSorteo']}
                            records = list(result.values())
                            ##eliminar elementos vacios de la lista, por ejemplo {}
                            records = [x for x in records if x != {}]
                            self.estadoActivo(records, cuota)
                elif self.vars["countLinea"] == 2:
                    self.patchZohoRecord(self.vars["id"],0,'Activo',"","",'')                   
            elif self.vars["estado"] == "Renunciado":
                self.vars["window_handles"] = self.driver.window_handles
                self.driver.find_element(
                    By.XPATH, "//input[@value='Motivo de Renuncia']"
                ).click()
                self.vars["ventanRenuncia"] = self.wait_for_window(5000)
                self.driver.switch_to.window(self.vars["ventanRenuncia"])
                self.vars["motivoRenuncia"] = self.driver.find_element(
                    By.XPATH, "//tr[4]/td[2]"
                ).text
                self.driver.close()
                self.driver.switch_to.window(self.vars["principal"])
                self.patchZohoRecord(self.vars["id"],cuota,'Renunciado',self.vars["motivoRenuncia"],"")       
            elif self.vars["estado"] == "Baja":  # Baja de solicitud
                self.patchZohoRecord(self.vars["id"], cuota, "Baja", "Baja", "",'')
            elif self.vars["estado"] == "Sin informacion":  # Sin informacion
                self.patchZohoRecord(self.vars["id"], cuota, "Activo", "Sin informacion", "",'')
            elif self.vars["estado"] == "Incompleto":  # Incompleto
                self.patchZohoRecord(self.vars["id"], cuota, "Incompleto", "Incompleto", "",'')
            else:  # se usa para cualquier opcion que no este contemplada dentro de todo codigo de ejecucion
                print(
                    "Solicitud: {ss} - Estado: No contemplado".format(
                        ss=self.vars["ss"]
                    )
                )
            totalChequeos += 1
        if cuota == 0:
            self.enviarMsjInicio("fin", totalChequeos,cuota)
            self.enviarMsjResumenCuota(cuota)
            self.resetCuotas()
            self.control(1)
            print("Fin de control de saldos C" + str(cuota))
        elif cuota == 1:
            self.enviarMsjInicio("fin", totalChequeos,cuota)
            self.enviarMsjResumenCuota(cuota)
            self.resetCuotas()
            print("Fin de control de saldos C" + str(cuota))
            self.enviarRechazos()

    def estadoRenunciado(self, record, cuotaChequeada):
        ##chequear si hay mas de un elemento en record, si es asi, eliminar el primer elemento, 
        if len(record) > 1:
            newRecord = record[1:]
        else:
            newRecord = record
        #condicional para ejecutar el for solo si newRecord es una lista y tiene elementos
        if isinstance(newRecord, list) and newRecord:
            for r in newRecord:
               #corroborar que el elento no este vacio, que no sea {} 
                if r != {}:
                    if isinstance(r, dict):
                        for r in record:
                            if r['cuota'] <= str(7):
                                if isinstance(r, dict):
                                    if r['estado'] == 'Renunciado':
                                        self.patchZohoRecord(r['id'], str(cuotaChequeada), 'Renunciado', r['motivo'], '', '')
                                    elif r['estado'] == 'activo' and r['importe'] != '$0.00':
                                        self.patchZohoRecord(r['id'], str(cuotaChequeada), 'Cobrado', '', r['nroSorteo'],)
                                    elif r['estado'] == 'activo' and r['importe'] == '$0.00':
                                        self.patchZohoRecord(r['id'], str(cuotaChequeada), 'Activo', '', '','')
                                    else:
                                        print(f"Estado {r['estado']} no contemplado en cuota: {r['cuota']}, Importe: {r['importe']}")
                                else:
                                    print(f"Elemento no válido en record: {r}")
 
    def estadoActivo(self, record,cuotaChequeada):
        
        #print(f"Cuota chequeada: {cuotaChequeada}")
        #print(f"Record: {record}")
        ##chequear si hay mas de un elemento en record, si es asi, eliminar el primer elemento, 
        if len(record) > 1:
            newRecord = record[1:]
        else:
            newRecord = record
        #condicional para ejecutar el for solo si newRecord es una lista y tiene elementos
        if isinstance(newRecord, list) and newRecord:
            for r in newRecord:
               #corroborar que el elento no este vacio, que no sea {} 
                if r != {}:
                    print(f"Elemento no vacio: {r}")
                    if isinstance(r, dict):
                        if r['cuota'] <= str(7):
                            print(f"Record: {r}")
                            if r['estado'] == 'rechazado':
                                self.patchZohoRecord(r['id'], r["cuota"], 'Rechazado', r['motivo'], '')
                            elif r['estado'] == 'activo' and r['importe'] != '$0.00':
                                self.patchZohoRecord(r['id'], r["cuota"], 'Cobrado', '', r['nroSorteo'])
                            elif r['estado'] == 'activo' and r['importe'] == '$0.00':
                                self.patchZohoRecord(r['id'], r["cuota"], 'Activo', '', '')
                            else:
                                print(f"Estado activo no contemplado en cuota: {r['cuota']}, Importe: {r['importe']}")
                        else:
                            print(f"Elemento no válido en newRecord: {r}")
                else:
                    print("Elemento vacio")
        else:
            print(f"Elemento no válido en newRecord: {newRecord}")

if __name__ == "__main__":
    test = TestSaldos()
    #test.postZohoToken()
    test.control(0)
