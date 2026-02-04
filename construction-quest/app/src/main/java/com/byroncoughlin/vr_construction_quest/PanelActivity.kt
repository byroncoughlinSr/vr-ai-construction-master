package com.byroncoughlin.vr_construction_quest

import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicText
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

class PanelActivity : ComponentActivity() {
    companion object {
        val materials: List<String> = listOf("Wood", "Concrete", "Steel", "Brick", "Glass")
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent { MaterialPalette() }
    }
}

@Composable
fun MaterialPalette() {
    val context = LocalContext.current

    Column(
        modifier = Modifier
            .clip(RoundedCornerShape(32.dp))
            .fillMaxSize()
            .background(Color(0xFF2C2C2C))
            .padding(16.dp),
        verticalArrangement = Arrangement.Top,
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        BasicText(
            text = "Material Palette",
            style = TextStyle(color = Color.White, fontSize = 30.sp, fontWeight = FontWeight.Bold),
            modifier = Modifier.padding(bottom = 20.dp)
        )
        Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
            PanelActivity.materials.forEach { material ->
                MaterialItem(
                    title = material,
                    onClick = {
                        val intent = Intent("com.byroncoughlin.CHANGE_MATERIAL")
                        intent.putExtra("selectedMaterial", material)
                        context.sendBroadcast(intent)
                    })
            }
        }
    }
}

@Composable
fun MaterialItem(title: String, onClick: () -> Unit) {
    Box(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(12.dp))
            .background(Color(0xFF4A4A4A))
            .clickable(onClick = onClick)
            .padding(16.dp),
        contentAlignment = Alignment.Center
    ) {
        BasicText(
            text = title,
            style = TextStyle(color = Color.White, fontSize = 22.sp)
        )
    }
}
