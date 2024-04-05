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

class TestSaldos:
    def __init__(self):
        load_dotenv()
        options = webdriver.ChromeOptions()
        options.add_argument("--ignore-certificate-errors")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--remote-debugging-port=9222")
        options.add_argument("--headless")
        options.add_argument("--log-level=3")  # Deshabilitar el registro del navegador
        self.driver = webdriver.Chrome(options=options)
        self.vars = {}
        self.activos = [] 
    #funcion para volver a 0 las variables de las cuotas
    def resetCuotas(self):
        self.cuotaRechazada = 0
        self.cuotaRenunciada = 0
        self.cuotaActiva = 0
        self.cuotaCobrada = 0
        self.cuotaBaja = 0
        self.cuotaSinInformacion = 0

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

    def saveRecordsToExcel(self,records, filename):
        df = pd.DataFrame(records)
        df.to_excel(filename, index=False)
    
    ##FUNCION PARA CREAR EL ARCHIVO DE EXCEL 
    def create_excel_file(self, records):
        df = pd.DataFrame(records)
        fecha_hoy = datetime.now().strftime('%d-%m-%Y')
        nombre_archivo = f"Rechazadas - {fecha_hoy}.xlsx"
        with pd.ExcelWriter(nombre_archivo) as writer:
            df.to_excel(writer, index=False, sheet_name="Rechazadas")
        return nombre_archivo
    
    ##funcion para obtener los leads activos desde extranet
    def getActivos(self):
        self.vars["usuario"] = os.environ.get("AUTOGESTION_USER")
        self.vars["password"] = os.environ.get("AUTOGESTION_PASSWORD")
        self.vars['ss1'] = '5'
        self.vars['ss2'] = '0617002'
        
        #armar un blucle autoincremental de 1000 pasos para obtener los leads activos, ir incrementado la ss de a 1
        for i in range(20000):
            self.vars["id"] = i
            self.vars["ss2"] = str(int(self.vars["ss2"]) + 1)  # Convertir a entero, incrementar y convertir a cadena
            if len(self.vars["ss2"]) < 7:
                self.vars["ss2"] = '0' * (7 - len(self.vars["ss2"])) + self.vars["ss2"]  # Rellenar con ceros a la izquierda si es necesario
            self.vars["ss"] = f"{self.vars['ss1']}/{self.vars['ss2']}"
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
            #time.sleep(3)
            try:
                self.vars["estado"] = self.driver.find_element(
                By.XPATH, "//tr[33]/td[2]"
            ).text
            except:
                self.vars["estado"] = "Sin informacion"
            #imprimir el numero de ss, el numero del loop y el estado
            print(f"SS: {self.vars['ss']} - Loop: {i} - Estado: {self.vars['estado']}")
            if self.vars["estado"] == "Activo":
                try:
                    self.vars["nroSorteo"] = self.driver.find_element(By.XPATH, "//tr[5]/td[2]").text
                except:
                    self.vars["nroSorteo"] = 0
                #extraer todas los datos del contacto
                self.vars["nombre"] = self.driver.find_element(By.XPATH, "//tr[6]/td[2]").text
                self.vars["dni"] = self.driver.find_element(By.XPATH, "//tr[7]/td[2]").text
                self.vars["calle"] = self.driver.find_element(By.XPATH, "//tr[8]/td[2]").text
                self.vars["cp"] = self.driver.find_element(By.XPATH, "//tr[11]/td[2]").text
                self.vars["localidad"] = self.driver.find_element(By.XPATH, "//tr[12]/td[2]").text
                self.vars["provincia"] = self.driver.find_element(By.XPATH, "//tr[13]/td[2]").text
                self.vars["telefono"] = self.driver.find_element(By.XPATH, "//tr[14]/td[2]").text
                self.vars["celular"] = self.driver.find_element(By.XPATH, "//tr[15]/td[2]").text
                self.vars["email"] = self.driver.find_element(By.XPATH, "//tr[16]/td[2]").text
                self.vars["nacimiento"] = self.driver.find_element(By.XPATH, "//tr[17]/td[2]").text
                self.vars["trabajo"] = self.driver.find_element(By.XPATH, "//tr[18]/td[2]").text
                self.vars["titular_cuenta_banco"] = self.driver.find_element(By.XPATH, "//tr[20]/td[2]").text
                self.vars["fecha_alta"] = self.driver.find_element(By.XPATH, "//tr[21]/td[2]").text
                self.vars["codigo_articulo"] = self.driver.find_element(By.XPATH, "//tr[23]/td[2]").text
                self.vars["articulo"] = self.driver.find_element(By.XPATH, "//tr[24]/td[2]").text
                self.vars["valor_nominal"] = self.driver.find_element(By.XPATH, "//tr[26]/td[2]").text
                self.vars["cuotas_emitidas"] = self.driver.find_element(By.XPATH, "//tr[28]/td[2]").text
                self.vars["cuotas_pagas"] = self.driver.find_element(By.XPATH, "//tr[29]/td[2]").text
                self.vars["convenio"] = self.driver.find_element(By.XPATH, "//tr[30]/td[2]").text
                self.vars["zona_venta"] = self.driver.find_element(By.XPATH, "//tr[31]/td[2]").text
                self.vars["productor"] = self.driver.find_element(By.XPATH, "//tr[32]/td[2]").text
                self.vars["estado"] = self.driver.find_element(By.XPATH, "//tr[33]/td[2]").text
                
                # Guardar los datos en el diccionario activos
                activo = {
                    "nombre": self.vars["nombre"],
                    "dni": self.vars["dni"],
                    "ss": self.vars["ss"],
                    "sorteo": self.vars["nroSorteo"],
                    "estado": self.vars["estado"],
                    "telefono": self.vars["telefono"],
                    "celular": self.vars["celular"],
                    "email": self.vars["email"],
                    "nacimiento": self.vars["nacimiento"],
                    "trabajo": self.vars["trabajo"],
                    "titular_cuenta_banco": self.vars["titular_cuenta_banco"],
                    "fecha_alta": self.vars["fecha_alta"],
                    "codigo_articulo": self.vars["codigo_articulo"],
                    "articulo": self.vars["articulo"],
                    "valor_nominal": self.vars["valor_nominal"],
                    "cuotas_emitidas": self.vars["cuotas_emitidas"],
                    "cuotas_pagas": self.vars["cuotas_pagas"],
                    "convenio": self.vars["convenio"],
                    "zona_venta": self.vars["zona_venta"],
                    "productor": self.vars["productor"],
                    "fecha_datos": datetime.now().strftime('%d-%m-%Y')
                }
                self.activos.append(activo)
                ##
        
        #guardar los datos en un archivo de excel, archivo con la fecha de hoy en el nombre
        #crear file name en base a la fecha de hoy
        fileName = f"Activos-{datetime.now().strftime('%d-%m-%Y')}.xlsx"
        self.saveRecordsToExcel(self.activos, fileName)

if __name__ == "__main__":
    test = TestSaldos()
    test.getActivos()
