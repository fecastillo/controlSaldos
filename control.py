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

'''
class LogFile(io.TextIOWrapper):
    def write(self, s):
        timestamp = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
        super().write(f"{timestamp} {s}")
'''

class TestSaldos:
    def __init__(self):
        load_dotenv()
        #self.log_file = open("output.log", "a")
        #sys.stdout = LogFile(self.log_file.buffer)
        #sys.stderr = LogFile(self.log_file.buffer)
        #self.log_file = open("output.log", "a")
        #sys.stdout = LogFile(self.log_file.buffer)
        #sys.stderr = LogFile(self.log_file.buffer)
        options = webdriver.ChromeOptions()
        options.add_argument("--ignore-certificate-errors")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--remote-debugging-port=9222")
        options.add_argument("--headless")
        options.add_argument("--log-level=3")  # Deshabilitar el registro del navegador
        self.driver = webdriver.Chrome(options=options)
        self.vars = {}

    #def __del__(self):
        #self.log_file.close()

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

    def getZohoRecord(self, cuota):
        # obtengo el numero del dia de hoy
        today = datetime.today().day
        if today >= 8 and today <= 31:
            # al mes corriente le resto 1 para obtener el mes anterior
            month = datetime.today().month
            if month == 1:
                month = 12
            else:
                month = month - 1
        # creo una lista de los meses del año para obtener el nombre del mes anterior
        months = [
            "zero",
            "Enero",
            "Febrero",
            "Marzo",
            "Abril",
            "Mayo",
            "Junio",
            "Julio",
            "Agosto",
            "Septiembre",
            "Octubre",
            "Noviembre",
            "Diciembre",
        ]
        # obtengo el nombre del mes anterior
        monthName = months[month]
        # Solicitar el access token de zoho
        access_token = self.getZohoToken()
        # URL de la API de Zoho creator
        url = 'https://creator.zoho.com/api/v2/autocredito/autocredito/report/Bot_{cuota}?from=0&limit=1&criteria=(Campa_a!="{month}")'.format(
            month=monthName, cuota=cuota
        )
        # &criteria=(Campa_a!='Abril')
        headers = {"Authorization": "Zoho-oauthtoken " + access_token}
        response = requests.get(url, headers=headers)
        if response.json().get("code") == 3000:
            hayRegistros = True
            ss = response.json().get("data")[0]["SS_completa"]
            id = response.json().get("data")[0]["ID"]
            # print("SS: ", ss, "ID: ", id, "Hay registros: ", hayRegistros)
            return ss, id, hayRegistros
        elif response.json().get("code") == 1030:
            hayRegistros = "expired"
            return hayRegistros
        elif response.json().get("code") == 4000:
          # terminar ejecucion del script por el limite de api de zoho
            print("Limite de API de Zoho alcanzado")
            print(response.json())
            exit()
        else:
            hayRegistros = False
            # print("No hay registros")
            # print(response.json())
            return '', '', hayRegistros

    def getAllZohoRecords(self, cuota):
        # obtengo el numero del dia de hoy
        day = datetime.today().day
        if day >= 1 and day <= 31:
            # al mes corriente le resto 1 para obtener el mes anterior
            month = datetime.today().month
            if month == 1:
                month = 12
            else:
                month = month - 1
        # obtengo el nombre del mes anterior
        monthName = datetime(datetime.today().year, month, 1).strftime('%B')
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
                    
                elif response_json.get("code") == 1030:
                    #print("Access token expirado, se esta obteniendo uno nuevo...")
                    self.postZohoToken()
                    records = self.getAllZohoRecords(cuota)
                    return records
                    
                elif response_json.get("code") == 4000:
                    # terminar ejecucion del script por el limite de api de zoho
                    print("Limite de API de Zoho alcanzado")
                    print(response.json())
                    exit()
                    
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
            }
            # print(datos)
            return datos
        elif response.json().get("code") == 1030:
            print("El access token ha expirado, se procede a obtener uno nuevo")
            self.postZohoToken()
            self.getOneZohoRecord(id)
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
            }
            # print(datos)
            return datos
        else:
            hayRegistros = False
            print("No hay registros")
            # print(response.json())
            return hayRegistros

    def patchZohoRecord(self, id, cuota, estado, motivo, sorteo):
        access_token = self.getZohoToken()
        data = {None}
        fecha = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        url = "https://creator.zoho.com/api/v2/autocredito/autocredito/report/Copy_of_Reporte_de_venta_Organizadores/{}".format(
            id
        )
        headers = {"Authorization": "Zoho-oauthtoken " + access_token}
        if estado == "Cobrado":
            if cuota == 0 or cuota == '0':
                if sorteo == 0 or sorteo == '0' or sorteo == '' or sorteo == None:
                    data = {
                    "data": {"Pago_saldo_01": "Pagado - Sin Nro", "Pago_saldo_02":"Pendiente", "Nro_de_Sorteo": 000, "fecha_actualizacion_saldos": fecha}
                }
                else:
                    data = {
                        "data": {
                            "Pago_saldo_01": "Pagado",
                            "Pago_saldo_02":"Pendiente",
                            "Nro_de_Sorteo": sorteo,
                            "fecha_actualizacion_saldos": fecha,
                        }
                    }
            elif cuota == 1:
                data = {
                    "data": {
                        "Pago_saldo_02": "Pagado",
                        "Nro_de_Sorteo": sorteo,
                        "fecha_actualizacion_saldos": fecha,
                    }
                }
            else:
                data = {
                    "data": {"Pago_saldo_01": "Pagado - Sin Nro","Pago_saldo_02":"Pendiente", "Nro_de_Sorteo": 000, "fecha_actualizacion_saldos": fecha}
                }
        elif estado == "Rechazado":
            if cuota == 0:
                data = {
                    "data": {
                        "Pago_saldo_01": "Rechazado",
                        "Motivo_renuncia_saldo": motivo,
                        "Pago_saldo_02": "Rechazo - C0",
                        "fecha_actualizacion_saldos": fecha,
                    }
                }
            elif cuota == 1:
                data = {
                    "data": {
                        "Pago_saldo_02": "Rechazado",
                        "Motivo_renuncia_saldo": motivo,
                        "fecha_actualizacion_saldos": fecha,
                    }
                }
        elif estado == "Renunciado":
            if cuota == 0:
                data = {
                    "data": {
                        "Pago_saldo_01": "Renunciado",
                        "Pago_saldo_02": "Renunciado",
                        "Motivo_renuncia_saldo": motivo,
                        "fecha_actualizacion_saldos": fecha,
                    }
                }
            elif cuota == 1:
                data = {
                    "data": {
                        "Pago_saldo_02": "Renunciado",
                        "Motivo_renuncia_saldo": motivo,
                        "fecha_actualizacion_saldos": fecha,
                    }
                }
        elif estado == "Activo":
            if cuota == 0:
                data = {
                    "data": {
                        "Pago_saldo_01": "Sin informacion",
                        "fecha_actualizacion_saldos": fecha,
                    }
                }
            elif cuota == 1:
                data = {
                    "data": {
                        "Pago_saldo_02": "Sin informacion",
                        "fecha_actualizacion_saldos": fecha,
                    }
                }
        elif estado == "Baja":
            if cuota == 0 or cuota == '0':
                data = {
                    "data": {
                        "Pago_saldo_01": "Baja",
                        "Motivo_renuncia_saldo": motivo,
                        "Pago_saldo_02": "Baja",
                        "fecha_actualizacion_saldos": fecha,
                    }
                }
            elif cuota == 1:
                data = {
                    "data": {
                        "Pago_saldo_02": "Baja",
                        "Motivo_renuncia_saldo": motivo,
                        "fecha_actualizacion_saldos": fecha,
                    }
                }
        elif estado == "Sin informacion":
            data = {
                    "data": {
                        "fecha_actualizacion_saldos": fecha,
                    }
                }
        #evito que data se envio vacio
        #print(data)
        if data != {None}:
            #print(data)
            json_data = json.dumps(data)
            response = requests.patch(url, headers=headers, data=json_data)
            print(response.json())
            if response.json().get("code") == 1030:
                print("Token expirado, se esta obteniendo uno nuevo...")
                self.postZohoToken()
                access_token = self.getZohoToken()
                response = requests.patch(url, headers=headers, data=json_data)
                print(response.json())
        else:
            print("No se envio nada, data vacio")
        # enviar mensaje solo si el estado es distinto de activo y si la fecha del dia esta comprendida entre el 8 y el 31 de cada mes
        if estado != "Activo" and datetime.now().day >= 10:
         self.enviarMsj(id, cuota, estado, motivo, sorteo)

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
                if "code" in data and data["code"] == 1030:
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
        access_token = self.getZohoToken()
        url = "https://creator.zoho.com/api/v2/autocredito/autocredito/report/Rechazos_Bot"
        headers = {"Authorization": "Zoho-oauthtoken " + access_token}
        
        records = self.get_records_from_zoho(url, headers, 200)
        
        fecha_hoy = datetime.now().strftime('%d-%m-%Y')
        
        nombre_archivo = self.create_excel_file(records)
        
        from_email=os.environ.get("SENDGRID_FROM_EMAIL")
        to_emails=[To('fernando@grupogf2.com.ar'),To('gonzalo.pero@grupogf2.com.ar'),To('florencia.pero@autocredito.net.ar'),To('emmanuel.aleman@autocredito.net.ar')]
        subject=f"Rechazadas - {fecha_hoy}"
        html_content="<strong>Se adjuntan los saldos rechazados</strong>"
        
        sendgrid_api_key=os.environ.get("SENDGRID_API_KEY")
        #print(sendgrid_api_key)
        #print(from_email)
        #print(to_emails)
        self.send_email_with_attachment(sendgrid_api_key, from_email, to_emails, subject, html_content, nombre_archivo)
        
    def enviarMsjCBU(self):
        msj = "CUIT: 33-70495331-9 Nación Cbu: 0110553720055300055274 -  Santander Cbu: 0720463420000000180436 - BBVA Cbu: 0170294320000000129987 - Macro Cbu: 2850865630000000631641"
        url = os.environ.get("TELEGRAM_URL")
        data = {"chat_id": os.environ.get("TELEGRAM_CHAT_ID")}
        data["text"] = msj
        requests.post(url, data=data)
        
    def enviarMsj(self, id, cuota, estado, motivo, sorteo):
        print(f"Estado en msj: {estado}")
        msj = ""
        record = self.getOneZohoRecord(id)
        fecha = datetime.now().strftime("%d/%m/%Y")
        url = os.environ.get("TELEGRAM_URL")
        data = {"chat_id": os.environ.get("TELEGRAM_CHAT_ID")}
        if estado == "Cobrado" or estado == "cobrado":
            msj = "En el dia: {fecha}, se aprobó el cobro de CUOTA {cuota} del cliente: {dni} - {nombre}. Organizador: {organizador}, Productor: {productor}. Nro de sorteo: {sorteo}. Fecha de nacimiento: {nacimiento}. Valor nominal: {valorNominal}. SS: {ss}".format(
                fecha=fecha,
                cuota=cuota,
                dni=record["dni"],
                nombre=record["nombre"],
                organizador=record["organizador"],
                productor=record["productor"],
                sorteo=sorteo,
                nacimiento=record["nacimiento"],
                valorNominal=record["valorNominal"],
                ss=record["ss"],
            )
            # print("aprobado")
        elif estado == "Rechazado" or estado == "rechazado":
            msj = "En el dia: {fecha}, se rechazó el cobro de CUOTA {cuota} del cliente: {dni} - {nombre}. Motivo: {motivo}. Organizador: {organizador}, Productor: {productor}. Fecha de nacimiento: {nacimiento}. Valor nominal: {valorNominal}. SS: {ss}".format(
                fecha=fecha,
                cuota=cuota,
                dni=record["dni"],
                nombre=record["nombre"],
                motivo=motivo,
                organizador=record["organizador"],
                productor=record["productor"],
                nacimiento=record["nacimiento"],
                valorNominal=record["valorNominal"],
                ss=record["ss"],
            )
            # print("rechazado", record['ss'])
        elif estado == "Renunciado" or estado == "renunciado":
            msj = "En el dia: {fecha}, el cliente: {dni} - {nombre}, renunció al plan en CUOTA {cuota}. Organizador: {organizador}, Productor: {productor}.".format(
                fecha=fecha,
                cuota=cuota,
                dni=record["dni"],
                nombre=record["nombre"],
                organizador=record["organizador"],
                productor=record["productor"],
            )
        elif estado == "Baja" or estado == "baja":
            msj = "Se dió de baja en el dia: {fecha}, el cliente: {dni} - {nombre}. Organizador: {organizador}, Productor: {productor}.".format(
                fecha=fecha,
                cuota=cuota,
                dni=record["dni"],
                nombre=record["nombre"],
                organizador=record["organizador"],
                productor=record["productor"],
            )
            # print('Renunciado')
        # print(record)
        # insertar variable msj en data
        #print(msj)
        if msj and cuota == 1:
            data["text"] = msj
            requests.post(url, data=data)
            self.enviarMsjCBU()
        elif msj and cuota != 1:
            data["text"] = msj
            requests.post(url, data=data)
        #print("Mensaje enviado")
    
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
        #print(response.json())

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
        #self.enviarMsjInicio("inicio",totalRecords,cuota)
        self.enviarMsjInicio("inicio",totalRecords,cuota)
        for record in records:
            estadoViejo = record['Pago_saldo_01'] if cuota == 0 else record['Pago_saldo_02']
            #print(f"Estado viejo: {estadoViejo}")
            self.vars["id"] = record['ID']
            self.vars["ss"] = record['SS_completa']
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
                    "https://agencias.autocredito.com/extranet/agencias/consultas/ctacte.asp?nro_pre=5&nro_ingres={nroIngres}".format(
                        nroIngres=self.vars["nro_ingres"]
                    )
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
                        print(f"cuotaRow: {cuotaRow}, cuota: {cuota}, fecha pago: {fecha_pago}")
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
                        #solo ingresar si cuotaRow coincide con el numero de cuota
                        if int(cuotaRow) == cuota:
                            result[cuotaRow] = {'cuota': cuotaRow, 'importe': f"${sums[cuotaRow]:,.2f}", 'estado': estado or result[cuotaRow].get('estado', ''), 'motivo': codigo_rechazo or result[cuotaRow].get('motivo', ''), 'id': self.vars['id'], 'ss': self.vars['ss'], 'nroSorteo': self.vars['nroSorteo']}
                            records = list(result.values())
                            self.estadoActivo(records, estadoViejo)
                elif self.vars["countLinea"] == 2:
                    self.patchZohoRecord(self.vars["id"],0,'Activo',"","")                   
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
                ###chequeo todas cuotas para encontrar donde esta el rechazo
                self.driver.get(
                    "https://agencias.autocredito.com/extranet/agencias/consultas/ctacte.asp?nro_pre=5&nro_ingres={nroIngres}".format(
                        nroIngres=self.vars["nro_ingres"]
                    )
                )
                self.vars["countLinea"] = len(
                    self.driver.find_elements(By.XPATH, "//table[2]/tbody/tr")
                )
                if self.vars["countLinea"] > 2:
                    start_row = 4
                    end_row = self.vars['countLinea'] - 2
                    rows = self.driver.find_elements(By.XPATH, f"//table[2]/tbody/tr[position()>={start_row} and position()<={end_row}]")
                    sums = defaultdict(int)
                    result = defaultdict(dict)
                    for i, row in enumerate(rows, start=start_row):
                        first_cell = row.find_element(By.XPATH, "./td[1]")
                        cuotaRow = first_cell.text.strip()
                        fifth_cell = row.find_element(By.XPATH, "./td[5]")
                        imp_pagado = float(fifth_cell.text.replace('$', '').replace('.', '').replace(',', '.'))
                        sums[cuotaRow] += imp_pagado
                        tenth_cell = row.find_element(By.XPATH, "./td[10]")
                        sixth_cell = row.find_element(By.XPATH, "./td[6]")
                        fecha_pago = sixth_cell.text.strip()

                        link = tenth_cell.find_elements(By.XPATH, './/a[text()="ver motivo"]')
                        #poner estado solo si la fecha de pago existe
                        if fecha_pago == '':
                            estado = 'Renunciado'
                        elif fecha_pago != '':
                            estado = 'activo'
                        #estado = 'Renunciado' if fecha_pago else 'activo'
                        if estado == 'Renunciado':
                            codigo_rechazo = self.vars["motivoRenuncia"]
                        else:
                            codigo_rechazo = ''
                        #solo ingresar si cuotaRow coincide con el numero de cuota
                        if int(cuotaRow) == cuota:
                            result[cuotaRow] = {'cuota': cuotaRow, 'importe': f"${sums[cuotaRow]:,.2f}", 'estado': estado or result[cuotaRow].get('estado', ''), 'motivo': codigo_rechazo or result[cuotaRow].get('motivo', ''), 'id': self.vars['id'], 'ss': self.vars['ss'], 'nroSorteo': self.vars['nroSorteo']}
                            records = list(result.values())
                            self.estadoRenunciado(records)
                elif self.vars["countLinea"] == 2:
                    self.patchZohoRecord(self.vars["id"],0,'Renunciado',self.vars["motivoRenuncia"],"")       
            elif self.vars["estado"] == "Baja":  # Baja de solicitud
                self.patchZohoRecord(self.vars["id"], cuota, "Baja", "Baja", "")
            elif self.vars["estado"] == "Sin informacion":  # Sin informacion
                self.patchZohoRecord(self.vars["id"], cuota, "Activo", "Sin informacion", "")
            else:  # se usa para cualquier opcion que no este contemplada dentro de todo codigo de ejecucion
                print(
                    "Solicitud: {ss} - Estado: No contemplado".format(
                        ss=self.vars["ss"]
                    )
                )
            totalChequeos += 1
        if cuota == 0:
            self.enviarMsjInicio("fin", totalChequeos,0)
            self.control(1)
        else:
            self.enviarMsjInicio("fin", totalChequeos,1)
            self.enviarRechazos()
            print("Fin de control de saldos C" + str(cuota))
    def estadoRenunciado(self, record):
        for r in record:
            if isinstance(r, dict):
                if r['estado'] == 'Renunciado' and r['cuota'] == '0':
                    self.patchZohoRecord(r['id'], 0, 'Renunciado', r['motivo'], '')
                elif r['estado'] == 'Renunciado' and r['cuota'] == '1':
                    self.patchZohoRecord(r['id'], 1, 'Renunciado', r['motivo'], '')
                elif r['estado'] == 'activo' and r['importe'] != '$0.00' and r['cuota'] == '0':
                    self.patchZohoRecord(r['id'], 0, 'Cobrado', '', r['nroSorteo'])
                elif r['estado'] == 'activo' and r['importe'] != '$0.00' and r['cuota'] == '1':
                    self.patchZohoRecord(r['id'], 1, 'Cobrado', '', r['nroSorteo'])
                elif r['estado'] == 'activo' and r['importe'] == '$0.00' and r['cuota'] == '0':
                    self.patchZohoRecord(r['id'], 0, 'Activo', '', '')
                elif r['estado'] == 'activo' and r['importe'] == '$0.00' and r['cuota'] == '1':
                    self.patchZohoRecord(r['id'], 1, 'Activo', '', '')
                else:
                    print(f"Estado {r['estado']} no contemplado en cuota: {r['cuota']}, Importe: {r['importe']}")
            else:
                print(f"Elemento no válido en record: {r}")
 
    def estadoActivo(self, record, estadoViejo):
        if len(record) > 1:
            newRecord = record[1:]
        else:
            newRecord = record

        for r in newRecord:
            print(r)
            if isinstance(r, dict):
                if r['estado'] == 'rechazado' and r['cuota'] == '0' and estadoViejo != 'Rechazado':
                    self.patchZohoRecord(r['id'], 0, 'Rechazado', r['motivo'], '')
                elif r['estado'] == 'rechazado' and r['cuota'] == '0' and estadoViejo == 'Rechazado':
                    self.patchZohoRecord(r['id'], 0, 'Sin informacion', r['motivo'], '')
                elif r['estado'] == 'rechazado' and r['cuota'] == '1' and estadoViejo != 'Rechazo - C0':
                    self.patchZohoRecord(r['id'], 1, 'Rechazado', r['motivo'], '')
                elif r['estado'] == 'rechazado' and r['cuota'] == '1' and estadoViejo == 'Rechazo - C0':
                    self.patchZohoRecord(r['id'], 0, 'Sin informacion', r['motivo'], '')
                elif r['estado'] == 'activo' and r['importe'] != '$0.00' and r['cuota'] == '0':
                    self.patchZohoRecord(r['id'], 0, 'Cobrado', '', r['nroSorteo'])
                elif r['estado'] == 'activo' and r['importe'] != '$0.00' and r['cuota'] == '1':
                    self.patchZohoRecord(r['id'], 1, 'Cobrado', '', r['nroSorteo'])
                elif r['estado'] == 'activo' and r['importe'] == '$0.00' and r['cuota'] == '0':
                    self.patchZohoRecord(r['id'], 0, 'Activo', '', '')
                elif r['estado'] == 'activo' and r['importe'] == '$0.00' and r['cuota'] == '1':
                    self.patchZohoRecord(r['id'], 1, 'Activo', '', '')
                else:
                    print(f"Estado activo no contemplado en cuota: {r['cuota']}, Importe: {r['importe']}")
            else:
                print(f"Elemento no válido en newRecord: {r}")

if __name__ == "__main__":
    test = TestSaldos()
    test.control(0)
