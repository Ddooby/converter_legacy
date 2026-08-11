// 날짜 변환함수
// YYYY-MM-DDTHH:hh:ss -> YYYYMMDD
com.dateFormatString = function (objDate, strFormat)
{
	if (com.isNull(objDate)) {
		return;
	}

    if (com.isNull(strFormat)) {
        strFormat = "%Y%m%d";
    }

    if ((objDate instanceof Date == false) && (objDate instanceof nexacro.Date == false)) {
        if (/^\d{8,14}$/.test(objDate)) {
            // YYYYMMDD(필수) 뒤에 HHMMSS 가 없거나 일부만 있어도 남는 자릿수는 0으로 채워서 14자리로 맞춤
            var sDT = (objDate + "00000000000000").substr(0, 14);
            objDate = sDT.substr(0,4) + "-" + sDT.substr(4,2) + "-" + sDT.substr(6,2) + " " + sDT.substr(8,2) + ":" + sDT.substr(10,2) + ":" + sDT.substr(12,2);
        }
        objDate = new Date(objDate);
    }

    var fY = String(objDate.getFullYear());
    var fY2 = fY.substr(fY.length-2, 2);

    strFormat = strFormat.toString();
    strFormat = strFormat.split("%Y").join(String(objDate.getFullYear()));
    strFormat = strFormat.split("%y").join(fY2);
    strFormat = strFormat.split("%m").join(String(objDate.getMonth() + 1).padLeft(2, "0"));
    strFormat = strFormat.split("%d").join(String(objDate.getDate()).padLeft(2, "0"));
    strFormat = strFormat.split("%H").join(String(objDate.getHours()).padLeft(2, "0"));
    strFormat = strFormat.split("%M").join(String(objDate.getMinutes()).padLeft(2, "0"));
    strFormat = strFormat.split("%S").join(String(objDate.getSeconds()).padLeft(2, "0"));

    return strFormat;
};